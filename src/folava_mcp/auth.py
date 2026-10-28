"""Canvas authorization kept outside the model-visible MCP surface.

The Canvas data client remains GET-only. OAuth exchange, refresh and explicit
revocation are isolated here and always use the configured origin's fixed path.
"""

from __future__ import annotations

import hmac
import json
import math
import os
import secrets
import time
import uuid
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import keyring

from .config import (
    ConfigError,
    Profile,
    load_profile,
    normalize_origin,
    profile_lock,
    read_token_file,
    remove_profile,
    save_profile,
    validate_profile_name,
)


class AuthError(ConfigError):
    """A credential problem with a deliberately secret-free message."""


@dataclass(frozen=True)
class Credentials:
    origin: str
    token: str = field(repr=False)


def secure_keyring() -> Any:
    """Select an OS-backed credential store; never a plaintext/plugin fallback."""
    try:
        backend = keyring.get_keyring()
        candidates = getattr(backend, "backends", [backend])
        for candidate in candidates:
            if (
                type(candidate).__module__
                in {
                    "keyring.backends.macOS",
                    "keyring.backends.Windows",
                    "keyring.backends.SecretService",
                    "keyring.backends.libsecret",
                }
                and candidate.priority > 0
            ):
                return candidate
    except Exception:
        pass
    raise AuthError(
        "No unlocked OS credential store is available. Enable Keychain, "
        "Windows Credential Manager or Secret Service; for headless use "
        "CANVAS_URL with CANVAS_TOKEN_FILE."
    )


def _service() -> str:
    return "folava-mcp"


def _get_secret(profile: Profile) -> dict[str, Any]:
    try:
        raw = secure_keyring().get_password(_service(), profile.credential_id)
        value = json.loads(raw or "null")
        if (
            not isinstance(value, dict)
            or value.get("origin") != profile.origin
            or value.get("user_id") != profile.user_id
        ):
            raise ValueError
        if not isinstance(value.get("access_token"), str) or not value["access_token"]:
            raise ValueError
        return value
    except AuthError:
        raise
    except Exception:
        raise AuthError(
            "Stored credential is missing or does not match this Canvas profile. Sign in again."
        ) from None


def _put_secret(profile: Profile, secret: dict[str, Any]) -> None:
    try:
        secure_keyring().set_password(_service(), profile.credential_id, json.dumps(secret))
    except AuthError:
        raise
    except Exception:
        raise AuthError(
            "The OS credential store could not save this credential. Unlock it and try again."
        ) from None


def _delete_secret(profile: Profile) -> None:
    try:
        backend = secure_keyring()
        if backend.get_password(_service(), profile.credential_id) is not None:
            backend.delete_password(_service(), profile.credential_id)
    except AuthError:
        raise
    except Exception:
        raise AuthError(
            "Could not remove the credential from the OS store. Unlock it and retry logout."
        ) from None


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=20, follow_redirects=False, trust_env=False)


def _auth_request(client, method: str, url: str, **kwargs) -> httpx.Response:
    """Bound credential responses before decoding, independently of resource reads."""
    headers = {"Accept-Encoding": "identity", **kwargs.pop("headers", {})}
    deadline = time.monotonic() + 20
    with client.stream(method, url, headers=headers, **kwargs) as response:
        if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
            raise AuthError("Canvas must honor uncompressed credential responses.")
        body = bytearray()
        for chunk in (
            [response.content]
            if response.is_stream_consumed
            else response.iter_raw(chunk_size=16384)
        ):
            if len(body) + len(chunk) > 262144 or time.monotonic() > deadline:
                raise AuthError("Canvas credential response exceeded its size or time limit.")
            body.extend(chunk)
        return httpx.Response(response.status_code, content=bytes(body), request=response.request)


def _validate_token(token: str) -> str:
    if not token or len(token) > 16384 or any(c.isspace() for c in token):
        raise AuthError("Token must be a non-empty value without whitespace.")
    return token


def verify_identity(origin: str, token: str) -> str:
    """Validate the token against its exact Canvas origin before storing it."""
    origin = normalize_origin(origin)
    _validate_token(token)
    try:
        with _http_client() as client:
            response = _auth_request(
                client,
                "GET",
                origin + "/api/v1/users/self/profile",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
        if response.status_code == 401:
            raise AuthError(
                "Canvas rejected the credential. Check the Canvas URL and token, or sign in again."
            )
        if response.status_code == 403:
            raise AuthError(
                "Canvas denied profile access. The developer key needs the GET "
                "users/:user_id/profile scope."
            )
        if response.status_code != 200:
            raise AuthError(
                f"Canvas profile verification failed (HTTP {response.status_code}). "
                "No credential was saved."
            )
        body = response.json()
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("id"), (int, str))
            or isinstance(body.get("id"), bool)
        ):
            raise ValueError
        return str(body["id"])
    except AuthError:
        raise
    except (httpx.HTTPError, ValueError, TypeError):
        raise AuthError(
            "Could not verify the Canvas profile securely. Check connectivity and "
            "the Canvas URL; no credential was saved."
        ) from None


def _store(name: str, profile: Profile, secret: dict[str, Any]) -> None:
    with profile_lock(name):
        try:
            previous = load_profile(name)
        except ConfigError:
            previous = None
        _put_secret(profile, secret)
        try:
            save_profile(name, profile)
        except Exception:
            _delete_secret(profile)
            raise
        if previous:
            _delete_secret(previous)


def login_token(origin: str, token: str, profile: str = "default") -> Profile:
    """Personal token mode is intended for the account owner's local testing."""
    validate_profile_name(profile)
    origin = normalize_origin(origin)
    secure_keyring()  # Fail before collecting any account information remotely.
    user_id = verify_identity(origin, token)
    metadata = Profile(
        origin=origin, auth_kind="personal-token", credential_id=uuid.uuid4().hex, user_id=user_id
    )
    _store(profile, metadata, {"origin": origin, "user_id": user_id, "access_token": token})
    return metadata


def _token_request(origin: str, fields: dict[str, str]) -> dict[str, Any]:
    try:
        with _http_client() as client:
            response = _auth_request(
                client,
                "POST",
                normalize_origin(origin) + "/login/oauth2/token",
                data=fields,
                headers={"Accept": "application/json"},
            )
        if response.status_code != 200:
            raise AuthError(
                f"Canvas authorization failed (HTTP {response.status_code}). "
                "Check the institution's developer key or sign in again."
            )
        value = response.json()
        if not isinstance(value, dict) or str(value.get("token_type", "")).lower() != "bearer":
            raise ValueError
        _validate_token(value.get("access_token", ""))
        expires = float(value.get("expires_in", 3600))
        if not math.isfinite(expires) or expires <= 0:
            raise ValueError
        value["expires_at"] = time.time() + expires
        return value
    except AuthError:
        raise
    except (httpx.HTTPError, ValueError, TypeError):
        raise AuthError(
            "Canvas authorization could not complete securely. Check connectivity and try again."
        ) from None


def validate_redirect_uri(uri: str) -> tuple[str, int, str]:
    try:
        parsed = urlsplit(uri)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username
            or parsed.password
            or not parsed.port
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
            or "\\" in uri
            or parsed.port < 1024
        ):
            raise ValueError
        return parsed.hostname, parsed.port, parsed.path
    except ValueError:
        raise AuthError(
            "OAuth redirect URI must use http://127.0.0.1:<port>/<path> with a "
            "port above 1023, registered on the institution's developer key."
        ) from None


def authorization_url(
    origin: str, client_id: str, redirect_uri: str, state: str, scopes: list[str]
) -> str:
    validate_redirect_uri(redirect_uri)
    if not client_id or not scopes or any(not x.startswith("url:GET|/api/v1/") for x in scopes):
        raise AuthError("OAuth requires a client ID and explicit Canvas GET scopes.")
    return (
        normalize_origin(origin)
        + "/login/oauth2/auth?"
        + urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "state": state,
                "scope": " ".join(dict.fromkeys(scopes)),
                "purpose": "Folava MCP read-only access",
            }
        )
    )


def parse_callback(query: str, expected_state: str) -> str:
    values = parse_qs(query, keep_blank_values=True)
    received = values.get("state", [])
    if len(received) != 1 or not hmac.compare_digest(received[0], expected_state):
        raise AuthError("OAuth callback state did not match. This callback was rejected.")
    if "error" in values:
        raise AuthError(
            "Canvas authorization was declined or could not complete. Start sign-in again."
        )
    codes = values.get("code", [])
    if len(codes) != 1 or not codes[0]:
        raise AuthError("OAuth callback did not include one authorization code.")
    return codes[0]


def receive_authorization_code(
    url: str,
    redirect_uri: str,
    state: str,
    *,
    timeout: float = 180,
    open_browser: bool = True,
    on_url: Callable[[str], None] | None = None,
) -> str:
    """Bind loopback before opening the browser; never log callback query strings."""
    host, port, path = validate_redirect_uri(redirect_uri)
    result: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path != path or self.headers.get("Host") != f"{host}:{port}":
                self.send_error(404)
                return
            try:
                code = parse_callback(parsed.query, state)
            except AuthError:
                values = parse_qs(parsed.query)
                received = values.get("state", [])
                if (
                    len(received) == 1
                    and hmac.compare_digest(received[0], state)
                    and "error" in values
                ):
                    result["error"] = "denied"
                # A forged callback must not terminate a legitimate pending login.
                self.send_response(400)
                message = b"Authorization callback rejected. Return to your terminal."
            else:
                result["code"] = code
                self.send_response(200)
                message = b"Canvas connected. You may close this tab and return to your terminal."
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(message)))
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(message)
            except OSError:
                pass

    class LoopbackServer(HTTPServer):
        def get_request(self) -> tuple[Any, Any]:
            connection, address = super().get_request()
            connection.settimeout(2)
            return connection, address

    try:
        with LoopbackServer((host, port), Callback) as server:
            server.timeout = min(0.5, timeout)
            if on_url:
                on_url(url)
            if open_browser:
                webbrowser.open(url)
            deadline = time.monotonic() + timeout
            while not result and time.monotonic() < deadline:
                server.handle_request()
    except OSError:
        raise AuthError(
            "Could not bind the OAuth loopback callback. Close the application "
            "using that port, or register another redirect URI."
        ) from None
    if "error" in result:
        raise AuthError("Canvas authorization was declined. Run auth oauth to try again.")
    if "code" not in result:
        raise AuthError("Canvas sign-in timed out. Run auth oauth again when ready.")
    return result["code"]


def login_oauth(
    origin: str,
    client_id: str,
    client_secret: str,
    scopes: list[str],
    *,
    profile: str = "default",
    redirect_uri: str = "http://127.0.0.1:8765/callback",
    open_browser: bool = True,
    on_url: Callable[[str], None] | None = None,
) -> Profile:
    validate_profile_name(profile)
    origin = normalize_origin(origin)
    secure_keyring()
    if not client_secret:
        raise AuthError("The institution's developer key client secret is required.")
    state = secrets.token_urlsafe(32)
    url = authorization_url(origin, client_id, redirect_uri, state, scopes)
    code = receive_authorization_code(
        url, redirect_uri, state, open_browser=open_browser, on_url=on_url
    )
    value = _token_request(
        origin,
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )
    refresh = value.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise AuthError(
            "Canvas did not issue a refresh token. Ask the institution to check its developer key."
        )
    user_id = verify_identity(origin, value["access_token"])
    metadata = Profile(
        origin, "oauth", uuid.uuid4().hex, user_id, client_id, redirect_uri, tuple(scopes)
    )
    _store(
        profile,
        metadata,
        {
            "origin": origin,
            "user_id": user_id,
            "access_token": value["access_token"],
            "refresh_token": refresh,
            "expires_at": value["expires_at"],
            "client_secret": client_secret,
        },
    )
    return metadata


def _refresh_if_needed(metadata: Profile, secret: dict[str, Any]) -> dict[str, Any]:
    if metadata.auth_kind == "oauth":
        try:
            expiry = float(secret["expires_at"])
            if not math.isfinite(expiry):
                raise ValueError
        except (KeyError, ValueError, TypeError):
            raise AuthError("OAuth expiry metadata is invalid. Sign in again.") from None
        if expiry <= time.time() + 60:
            if not secret.get("refresh_token") or not secret.get("client_secret"):
                raise AuthError("OAuth refresh credentials are missing. Sign in again.")
            value = _token_request(
                metadata.origin,
                {
                    "grant_type": "refresh_token",
                    "client_id": metadata.client_id or "",
                    "client_secret": secret["client_secret"],
                    "redirect_uri": metadata.redirect_uri or "",
                    "refresh_token": secret["refresh_token"],
                },
            )
            # Canvas normally reuses the original refresh token.
            secret.update(access_token=value["access_token"], expires_at=value["expires_at"])
            if value.get("refresh_token"):
                secret["refresh_token"] = value["refresh_token"]
            _put_secret(metadata, secret)
    return secret


def load_credentials(profile: str = "default") -> Credentials:
    validate_profile_name(profile)
    origin = os.environ.get("CANVAS_URL")
    token = os.environ.get("CANVAS_TOKEN")
    token_file = os.environ.get("CANVAS_TOKEN_FILE")
    if any(value is not None for value in (origin, token, token_file)):
        if not origin or bool(token) == bool(token_file):
            raise AuthError(
                "Headless authentication requires CANVAS_URL and exactly one of "
                "CANVAS_TOKEN or CANVAS_TOKEN_FILE."
            )
        return Credentials(
            normalize_origin(origin),
            _validate_token(read_token_file(token_file) if token_file else token or ""),
        )
    with profile_lock(profile):
        metadata = load_profile(profile)
        secret = _get_secret(metadata)
        secret = _refresh_if_needed(metadata, secret)
        return Credentials(metadata.origin, secret["access_token"])


def logout(profile: str = "default", *, revoke: bool = False) -> None:
    """Delete local secrets; revoke only on an explicit CLI request."""
    with profile_lock(profile):
        metadata = load_profile(profile)
        if revoke:
            secret = _refresh_if_needed(metadata, _get_secret(metadata))
            try:
                with _http_client() as client:
                    response = _auth_request(
                        client,
                        "DELETE",
                        metadata.origin + "/login/oauth2/token",
                        headers={"Authorization": f"Bearer {secret['access_token']}"},
                    )
                if response.status_code not in (200, 204):
                    raise AuthError(
                        f"Canvas revocation failed (HTTP {response.status_code}); "
                        "local credentials were retained. "
                        "Retry or use logout without --revoke."
                    )
            except httpx.HTTPError:
                raise AuthError(
                    "Canvas revocation could not connect; local credentials were "
                    "retained. Retry or use logout without --revoke."
                ) from None
        _delete_secret(metadata)
        remove_profile(profile)
