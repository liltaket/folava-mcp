"""Fail-closed URL and query policy shared by first pages and continuations."""

from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

from .catalog import DISABLED_OPERATIONS, OPERATIONS, Operation


class PolicyError(ValueError):
    """A request was rejected before contacting Canvas."""


def validate_origin(value: str) -> str:
    try:
        if not isinstance(value, str):
            raise PolicyError("Canvas origin must be an HTTPS origin.")
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
            or url.port not in (None, 443)
            or "\\" in value
            or any(ord(char) < 33 for char in value)
        ):
            raise PolicyError("Canvas origin must be an HTTPS origin with no path or credentials.")
        # TLS SNI and Host headers require ASCII; normalize IDN origins once.
        hostname = url.hostname.encode("idna").decode("ascii").lower()
        return "https://" + ("[" + hostname + "]" if ":" in hostname else hostname)
    except (ValueError, UnicodeError) as error:
        raise PolicyError("Canvas origin must be a valid HTTPS origin.") from error


def operation_path(operation: str, path: dict[str, str] | None) -> tuple[Operation, str]:
    if isinstance(operation, str) and operation in DISABLED_OPERATIONS:
        raise PolicyError(DISABLED_OPERATIONS[operation])
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise PolicyError("Unknown operation; use discover to find reviewed reads.")
    op = OPERATIONS[operation]
    if path is not None and not isinstance(path, dict):
        raise PolicyError("Path arguments must be an object.")
    values = path or {}
    if set(values) != set(op.required_path):
        raise PolicyError("Path arguments must exactly match the operation's required_path.")
    for key, value in values.items():
        pattern = r"[\w-]{1,200}" if key == "page_url" else r"[0-9]{1,20}"
        if key == "user_id":
            pattern = r"(?:self|[0-9]{1,20})"
        elif key == "event_id":
            pattern = r"(?:assignment_)?[0-9]{1,20}"
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise PolicyError("Path arguments must be simple identifiers or page slugs.")
    return op, op.path.format(**{key: quote(value, safe="") for key, value in values.items()})


def validate_query(op: Operation, query: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    allowed = set(op.query_keys) | {"page", "per_page", "bookmark", "cursor"}
    if query is not None and not isinstance(query, dict):
        raise PolicyError("Query must be an object.")
    for key, value in (query or {}).items():
        if not isinstance(key, str) or key not in allowed:
            raise PolicyError("Query parameter is not allowed for this operation.")
        values = value if isinstance(value, list) else [value]
        if not values or len(values) > 100 or (len(values) > 1 and not key.endswith("[]")):
            raise PolicyError("Invalid query array or duplicated scalar parameter.")
        converted = []
        for item in values:
            if type(item) not in (str, int, bool):
                raise PolicyError("Query values must be strings, integers or booleans.")
            text = str(item).lower() if isinstance(item, bool) else str(item)
            if len(text) > 2000 or any(ord(char) < 32 for char in text):
                raise PolicyError("Query value exceeds the allowed bounds.")
            # Reject broadly, including comma-separated and nested association syntax.
            if key.startswith("include") and any(
                name in text.lower() for name in ("read_status", "read_state")
            ):
                raise PolicyError(
                    "Read-state includes are forbidden because Canvas marks submissions as read."
                )
            converted.append(text)
        if key == "auto_mark_as_read" and converted != ["false"]:
            raise PolicyError("Automatic marking as read is forbidden.")
        if key == "per_page" and (not converted[0].isdigit() or not 1 <= int(converted[0]) <= 100):
            raise PolicyError("per_page must be between 1 and 100.")
        if (
            key == "context_codes[]"
            and op.id in ("calendar", "calendar_events", "user_calendar")
            and len(values) > 10
        ):
            raise PolicyError(
                "Canvas accepts at most ten calendar contexts; make separate requests."
            )
        if (
            key == "type"
            and op.id in ("calendar", "calendar_events", "user_calendar")
            and converted[0] not in ("event", "assignment")
        ):
            raise PolicyError("Calendar type must be event or assignment.")
        result[key] = converted if isinstance(value, list) else converted[0]
    if op.id == "conversation":
        result["auto_mark_as_read"] = "false"
    return result


def build_url(origin: str, op: Operation, path: str, query: dict[str, Any] | None) -> str:
    safe = validate_query(op, query)
    encoded = urlencode(safe, doseq=True)
    return origin + path + ("?" + encoded if encoded else "")


def validate_continuation(value: str, origin: str, op: Operation, path: str) -> str:
    try:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or url.netloc.lower() != urlsplit(origin).netloc
            or url.path != path
            or url.fragment
            or url.username
            or url.password
            or "\\" in value
            or any(ord(char) < 33 for char in value)
        ):
            raise PolicyError("Unsafe pagination link was rejected.")
        query: dict[str, Any] = {}
        for key, item in parse_qsl(url.query, keep_blank_values=True, strict_parsing=True):
            if key.endswith("[]"):
                query.setdefault(key, []).append(item)
            elif key in query:
                raise PolicyError("Duplicate pagination parameter was rejected.")
            else:
                query[key] = item
        return build_url(origin, op, path, query)
    except (ValueError, UnicodeError) as error:
        raise PolicyError("Unsafe pagination link was rejected.") from error


INSTFS_HOSTS = frozenset({"inst-fs-dub-prod.inscloudgate.net"})
INSTFS_CDN_HOST = "cdn.inst-fs-dub-prod.inscloudgate.net"


def _instfs_filename(path: str, *, cdn: bool = False) -> str | None:
    uuid = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    prefix = "/" if cdn else "/files/"
    match = re.fullmatch(rf"{prefix}{uuid}/((?:[A-Za-z0-9._~-]|%[0-9A-Fa-f]{{2}})+)", path)
    if not match or len(path) > 4096 or "%25" in path.lower():
        return None
    filename = unquote(match[1], errors="strict")
    if (
        filename.lower() in (".", "..", "metadata", "duplicate")
        or any(char in filename for char in ("/", "\\"))
        or any(ord(char) < 32 or ord(char) == 127 for char in filename)
    ):
        return None
    return match[1]


def _instfs_claims(value: str, *, cdn: bool = False) -> dict | None:
    """Filter capability structure, NOT verify signatures; the storage service does that."""
    token = re.fullmatch(r"([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)", value)
    if not token or len(value) > 16_384:
        return None

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate capability field")
            result[key] = value
        return result

    def decode(part):
        raw = base64.b64decode(part + "=" * (-len(part) % 4), altchars=b"-_", validate=True)
        return json.loads(raw, object_pairs_hook=unique_object)

    try:
        header, claims = decode(token[1]), decode(token[2])
        signature = base64.b64decode(
            token[3] + "=" * (-len(token[3]) % 4), altchars=b"-_", validate=True
        )
        expected_header = {"typ": "JWT", "alg": "HS512", **({"kid": "cdn"} if cdn else {})}
        expected_keys = {"iat", "exp", "resource", "jti"} | (
            {"tenant"} if cdn else {"user_id", "host"}
        )
        valid = (
            header == expected_header
            and len(signature) == 64
            and isinstance(claims, dict)
            and set(claims) == expected_keys
            and type(claims["iat"]) is int
            and type(claims["exp"]) is int
            and 0 <= claims["iat"] < claims["exp"]
            and isinstance(claims["jti"], str)
            and 1 <= len(claims["jti"]) <= 200
        )
        return claims if valid else None
    except (ValueError, UnicodeError, RecursionError):
        return None


def _instfs_content(url) -> bool:
    """Recognize only the reviewed anonymous, resource-bound public_url capability."""
    if _instfs_filename(url.path) is None or not url.query.startswith("token="):
        return False
    claims = _instfs_claims(url.query.removeprefix("token="))
    return bool(
        claims
        and claims["user_id"] is None
        and claims["host"] is None
        and claims["resource"] == url.path
    )


def _instfs_cdn_content(url, source) -> bool:
    """Only provider-directed delivery of the same filename; IDs may be remapped."""
    filename = _instfs_filename(url.path, cdn=True)
    if filename is None or filename != _instfs_filename(source.path):
        return False
    pairs = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
    params = dict(pairs)
    if len(pairs) != 2 or set(params) != {"token", "content_type"}:
        return False
    if not re.fullmatch(r"[A-Za-z0-9.+_-]{1,60}/[A-Za-z0-9.+_-]{1,60}", params["content_type"]):
        return False
    claims = _instfs_claims(params["token"], cdn=True)
    return bool(
        claims
        and claims["resource"] == url.path
        and isinstance(claims["tenant"], str)
        and 1 <= len(claims["tenant"]) <= 2000
    )


def validate_storage_download(
    value: str, canvas_origin: str, *, instfs_source: str | None = None
) -> str:
    """Allow audited S3 objects and a bounded InstFS content capability.

    Canvas public_url can fall back to /files/:id/download on local storage.
    That GET can change module completion even with preview=1. Other InstFS
    hosts/routes and custom endpoints remain unsupported. The exact reviewed CDN
    is accepted only immediately after a validated InstFS 302, with the same filename.
    """
    try:
        url = urlsplit(value)
        origin = validate_origin(url.scheme + "://" + url.netloc)
        region = r"[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+"
        endpoint = rf"s3(?:[.-]{region}|\.dualstack\.{region})?\.amazonaws\.com"
        host = url.hostname or ""
        cdn_allowed = False
        if host == INSTFS_CDN_HOST and instfs_source is not None:
            source = urlsplit(validate_storage_download(instfs_source, canvas_origin))
            cdn_allowed = source.hostname in INSTFS_HOSTS and _instfs_cdn_content(url, source)
        if (
            origin == canvas_origin
            or url.fragment
            or "\\" in value
            or any(ord(char) < 33 for char in value)
            or not (
                re.fullmatch(rf"(?:[a-z0-9][a-z0-9.-]*\.)?{endpoint}", host)
                or (host in INSTFS_HOSTS and _instfs_content(url))
                or cdn_allowed
            )
            or re.search(r"(?:^|/)files/[^/]+/(?:download|preview)(?:/|$)", url.path)
        ):
            raise PolicyError(
                "Canvas file routes are excluded; content requires supported S3 or InstFS storage."
            )
        return value  # Preserve the signed path/query exactly.
    except (ValueError, UnicodeError):
        raise PolicyError(
            "File content requires supported direct storage; this destination is unsupported."
        ) from None
