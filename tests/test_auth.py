import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from folava_mcp import auth
from folava_mcp.config import ConfigError, Profile, load_profile, save_profile


class MemoryKeyring:
    def __init__(self):
        self.items = {}

    def get_password(self, service, username):
        return self.items.get((service, username))

    def set_password(self, service, username, value):
        self.items[(service, username)] = value

    def delete_password(self, service, username):
        self.items.pop((service, username), None)


@pytest.fixture(autouse=True)
def clean_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLAVA_CONFIG_DIR", str(tmp_path / "config"))
    for name in ("CANVAS_URL", "CANVAS_TOKEN", "CANVAS_TOKEN_FILE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def memory(monkeypatch):
    backend = MemoryKeyring()
    monkeypatch.setattr(auth, "secure_keyring", lambda: backend)
    return backend


def mock_http(monkeypatch, handler):
    monkeypatch.setattr(
        auth,
        "_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
    )


def test_reject_plaintext_backend(monkeypatch):
    backend = MemoryKeyring()
    monkeypatch.setattr(auth.keyring, "get_keyring", lambda: backend)
    with pytest.raises(auth.AuthError, match="OS credential store"):
        auth.secure_keyring()


def test_token_login_rotation_and_origin_binding(memory, monkeypatch, tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"id": 42, "name": "Student"})

    mock_http(monkeypatch, handler)
    auth.login_token("https://school.example/", "first-secret")
    first = load_profile()
    assert auth.load_credentials().token == "first-secret"
    auth.login_token("https://school.example", "second-secret")
    assert auth.load_credentials().token == "second-secret"
    assert len(memory.items) == 1
    assert first.credential_id != load_profile().credential_id
    assert all(request.method == "GET" for request in requests)
    assert "secret" not in (tmp_path / "config" / "profiles.json").read_text()
    current = load_profile()
    save_profile(
        "default",
        Profile("https://other.example", current.auth_kind, current.credential_id, current.user_id),
    )
    with pytest.raises(auth.AuthError, match="does not match"):
        auth.load_credentials()


def test_redirect_verification_does_not_leak_token(memory, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.example/"})

    mock_http(monkeypatch, handler)
    with pytest.raises(auth.AuthError):
        auth.login_token("https://school.example", "never-follow")
    assert len(requests) == 1
    assert not memory.items


def test_environment_file_not_keyring(monkeypatch, tmp_path):
    path = tmp_path / "token"
    path.write_text("env-secret")
    path.chmod(0o600)
    monkeypatch.setenv("CANVAS_URL", "https://school.example")
    monkeypatch.setenv("CANVAS_TOKEN_FILE", str(path))
    credentials = auth.load_credentials()
    assert credentials.origin == "https://school.example"
    assert credentials.token == "env-secret"
    assert "env-secret" not in repr(credentials)
    monkeypatch.setenv("CANVAS_TOKEN", "conflict")
    with pytest.raises(auth.AuthError, match="exactly one"):
        auth.load_credentials()


@pytest.mark.parametrize(
    "query",
    [
        "code=secret",
        "code=secret&state=wrong",
        "code=a&code=b&state=expected",
        "code=a&state=expected&state=expected",
        "error=access_denied&state=expected",
    ],
)
def test_callback_rejects_invalid_or_forged_results(query):
    with pytest.raises(auth.AuthError) as error:
        auth.parse_callback(query, "expected")
    assert "secret" not in str(error.value)


def test_callback_state_and_authorization_scope():
    assert auth.parse_callback("code=one-use-code&state=expected", "expected") == "one-use-code"
    url = auth.authorization_url(
        "https://school.example",
        "client",
        "http://127.0.0.1:8765/callback",
        "random-state",
        ["url:GET|/api/v1/courses"],
    )
    query = parse_qs(urlsplit(url).query)
    assert query["state"] == ["random-state"]
    assert query["scope"] == ["url:GET|/api/v1/courses"]
    with pytest.raises(auth.AuthError):
        auth.authorization_url(
            "https://school.example",
            "client",
            "http://127.0.0.1:8765/callback",
            "state",
            ["url:POST|/api/v1/courses"],
        )


@pytest.mark.parametrize(
    "uri",
    [
        "https://evil.example/callback",
        "http://localhost:8765/callback",
        "http://127.0.0.1:80/callback",
        "http://user@127.0.0.1:8765/callback",
        "http://127.0.0.1:8765/callback?x=1",
    ],
)
def test_redirect_uri_restricted(uri):
    with pytest.raises(auth.AuthError):
        auth.validate_redirect_uri(uri)


def test_oauth_refresh_keeps_refresh_token_and_secret_private(memory, monkeypatch):
    profile = Profile(
        "https://school.example",
        "oauth",
        "a" * 32,
        "42",
        "client",
        "http://127.0.0.1:8765/callback",
    )
    save_profile("default", profile)
    auth._put_secret(
        profile,
        {
            "origin": profile.origin,
            "user_id": "42",
            "access_token": "expired",
            "expires_at": time.time() - 10,
            "refresh_token": "refresh-secret",
            "client_secret": "client-secret",
        },
    )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json={"access_token": "fresh-secret", "token_type": "Bearer", "expires_in": 3600}
        )

    mock_http(monkeypatch, handler)
    assert auth.load_credentials().token == "fresh-secret"
    assert auth.load_credentials().token == "fresh-secret"
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "https://school.example/login/oauth2/token"
    assert b"grant_type=refresh_token" in requests[0].content
    assert auth._get_secret(profile)["refresh_token"] == "refresh-secret"


def test_logout_only_remote_when_explicit(memory, monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json={"id": 42}))
    auth.login_token("https://school.example", "personal-secret")

    def forbid_network():
        raise AssertionError("local logout must not call Canvas")

    monkeypatch.setattr(auth, "_http_client", forbid_network)
    auth.logout()
    assert not memory.items
    with pytest.raises(ConfigError):
        load_profile()


def test_revoke_failure_retains_local_credentials(memory, monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json={"id": 42}))
    auth.login_token("https://school.example", "personal-secret")
    mock_http(monkeypatch, lambda request: httpx.Response(500, text="private-error-and-secret"))
    with pytest.raises(auth.AuthError) as error:
        auth.logout(revoke=True)
    assert "private-error" not in str(error.value)
    assert memory.items
    assert load_profile()


def test_oauth_login_code_exchange_and_secure_storage(memory, monkeypatch):
    captured = {}

    def receive(url, redirect_uri, state, **kwargs):
        query = parse_qs(urlsplit(url).query)
        assert query["state"] == [state]
        assert len(state) >= 40
        assert "client-secret" not in url
        return auth.parse_callback(f"code=one-use-code&state={state}", state)

    monkeypatch.setattr(auth, "receive_authorization_code", receive)

    def handler(request):
        if request.method == "POST":
            captured.update(parse_qs(request.content.decode()))
            return httpx.Response(
                200,
                json={
                    "access_token": "new-secret",
                    "token_type": "Bearer",
                    "refresh_token": "refresh-secret",
                    "expires_in": 3600,
                },
            )
        return httpx.Response(200, json={"id": 42})

    mock_http(monkeypatch, handler)
    auth.login_oauth(
        "https://school.example",
        "client",
        "client-secret",
        ["url:GET|/api/v1/users/:user_id/profile"],
    )
    assert captured["grant_type"] == ["authorization_code"]
    assert captured["code"] == ["one-use-code"]
    assert auth.load_credentials().token == "new-secret"
    metadata = load_profile()
    stored = auth._get_secret(metadata)
    assert stored["client_secret"] == "client-secret"
    assert metadata.auth_kind == "oauth"


def test_reserved_looking_profile_names_do_not_deadlock():
    import subprocess
    import sys
    import textwrap

    # A subprocess timeout makes the former second-flock deadlock a bounded failure.
    script = textwrap.dedent("""
        import httpx
        from folava_mcp import auth
        class Memory:
            def __init__(self): self.items = {}
            def get_password(self, service, name): return self.items.get(name)
            def set_password(self, service, name, value): self.items[name] = value
            def delete_password(self, service, name): self.items.pop(name, None)
        backend = Memory()
        auth.secure_keyring = lambda: backend
        auth._http_client = lambda: httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"id": 42})))
        auth.login_token("https://school.example", "test-token", profile="profiles")
        assert auth.load_credentials("profiles").token == "test-token"
        auth.logout("profiles")
    """)
    import os
    from pathlib import Path

    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    result = subprocess.run([sys.executable, "-c", script], timeout=5, capture_output=True, env=env)
    assert result.returncode == 0, result.stderr.decode()


def test_auth_response_compression_rejected_without_decoding(monkeypatch):
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            raise AssertionError("Encoded credential response must not be consumed")
            yield b""

    mock_http(
        monkeypatch,
        lambda request: httpx.Response(200, headers={"content-encoding": "gzip"}, stream=Stream()),
    )
    with pytest.raises(auth.AuthError, match="uncompressed"):
        auth.verify_identity("https://school.example", "secret")


def test_callback_unicode_state_is_rejected_without_type_error():
    with pytest.raises(auth.AuthError, match="state"):
        auth.parse_callback("code=private-code&state=%C3%A5", "ascii-state")


def test_scope_cannot_smuggle_a_write_scope_in_one_value():
    with pytest.raises(auth.AuthError, match="GET scopes"):
        auth.authorization_url(
            "https://school.example",
            "client",
            "http://127.0.0.1:8765/callback",
            "state",
            ["url:GET|/api/v1/courses url:POST|/api/v1/courses"],
        )


@pytest.fixture
def callback_server():
    """Real HTTP sockets; skip only when the execution sandbox forbids sockets."""
    import socket
    import threading
    from contextlib import contextmanager

    @contextmanager
    def start(timeout=2):
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
        except PermissionError:
            pytest.skip("Execution sandbox forbids loopback sockets")
        ready = threading.Event()
        finished = threading.Event()
        result = {}
        uri = f"http://127.0.0.1:{port}/callback"

        def worker():
            try:
                result["code"] = auth.receive_authorization_code(
                    "https://school.example/login/oauth2/auth",
                    uri,
                    "expected-state",
                    timeout=timeout,
                    open_browser=False,
                    on_url=lambda _: ready.set(),
                )
            except Exception as error:
                result["error"] = error
            finally:
                finished.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        assert ready.wait(2), result
        try:
            yield port, result, finished
        finally:
            thread.join(timeout + 2)
            assert not thread.is_alive(), "Callback listener failed to respect its deadline"

    return start


def _callback_http(port, target, *, hosts=None, method="GET"):
    import http.client

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.putrequest(method, target, skip_host=True)
        for host in hosts if hosts is not None else [f"127.0.0.1:{port}"]:
            connection.putheader("Host", host)
        connection.endheaders()
        response = connection.getresponse()
        body = response.read()
        return response.status, body
    finally:
        connection.close()


def test_real_callback_rejects_forgery_and_malformed_requests_then_succeeds(
    callback_server, capsys
):
    with callback_server() as (port, result, finished):
        for target, hosts, status in [
            ("/wrong?code=private-code&state=expected-state", None, 404),
            ("/callback?code=private-code&state=wrong", None, 400),
            ("/callback?code=private-code&state=%C3%A5", None, 400),
            ("/callback?code=%ZZ&state=expected-state", None, 400),
            ("/callback?code=x&state=expected-state&state=expected-state", None, 400),
            ("/callback?code=x&state=expected-state", ["evil.example"], 404),
            ("/callback?code=x&state=expected-state", [f"127.0.0.1:{port}", "evil.example"], 404),
            ("http://evil.example/callback?code=x&state=expected-state", None, 404),
            ("http://[", None, 400),
        ]:
            actual, body = _callback_http(port, target, hosts=hosts)
            assert actual == status
            assert b"private-code" not in body
            assert not finished.is_set()
        status, body = _callback_http(port, "/callback?code=accepted-code&state=expected-state")
        assert status == 200
        assert b"accepted-code" not in body
        assert finished.wait(1)
        assert result == {"code": "accepted-code"}
    assert "Traceback" not in capsys.readouterr().err


def test_real_callback_denial_finishes_without_waiting_for_timeout(callback_server):
    with callback_server() as (port, result, finished):
        assert _callback_http(port, "/callback?error=access_denied&state=expected-state")[0] == 400
        assert finished.wait(1)
        assert isinstance(result["error"], auth.AuthError)
        assert "declined" in str(result["error"])


def test_real_callback_timeout_bounds_idle_and_partial_connections(callback_server):
    import socket

    for partial_connection in (False, True):
        started = time.monotonic()
        with callback_server(timeout=0.1) as (port, result, finished):
            connection = None
            try:
                if partial_connection:
                    connection = socket.create_connection(("127.0.0.1", port), timeout=1)
                    connection.sendall(b"GET /callback?code=private-code HTTP/1.1\r\n")
                assert finished.wait(0.8)
                assert isinstance(result["error"], auth.AuthError)
                assert "timed out" in str(result["error"])
                assert time.monotonic() - started < 1
            finally:
                if connection:
                    connection.close()


@pytest.mark.parametrize(
    "query",
    [
        "code=x&state=expected&bad",
        "code=x&state=%FF",
        "code=%ZZ&state=expected",
        "code=x%0A&state=expected",
        "code=" + "x" * 4097 + "&state=expected",
        "code=x&state=expected&" + "a=b&" * 9,
    ],
)
def test_callback_malformed_query_is_a_safe_auth_error(query):
    with pytest.raises(auth.AuthError):
        auth.parse_callback(query, "expected")


def _expired_oauth_profile():
    profile = Profile(
        "https://school.example",
        "oauth",
        "a" * 32,
        "42",
        "client",
        "http://127.0.0.1:8765/callback",
    )
    save_profile("default", profile)
    auth._put_secret(
        profile,
        {
            "origin": profile.origin,
            "user_id": "42",
            "access_token": "expired",
            "expires_at": 1,
            "refresh_token": "refresh-secret",
            "client_secret": "client-secret",
        },
    )
    return profile


def test_concurrent_refreshes_exchange_once_and_share_new_token(memory, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    _expired_oauth_profile()
    requests = []
    barrier = threading.Barrier(4)

    def handler(request):
        requests.append(request)
        time.sleep(0.03)  # Hold the refresh while competing processes reach the file lock.
        return httpx.Response(
            200,
            json={
                "access_token": "fresh-secret",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    def load():
        barrier.wait(timeout=2)
        return auth.load_credentials().token

    mock_http(monkeypatch, handler)
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(lambda _: load(), range(4))) == ["fresh-secret"] * 4
    assert len(requests) == 1


def test_refresh_failure_keeps_previous_secret_and_can_retry(memory, monkeypatch):
    profile = _expired_oauth_profile()
    before = auth._get_secret(profile)
    mock_http(monkeypatch, lambda _: httpx.Response(400, json={"error": "private-secret"}))
    with pytest.raises(auth.AuthError) as error:
        auth.load_credentials()
    assert "private-secret" not in str(error.value)
    assert auth._get_secret(profile) == before
    mock_http(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json={
                "access_token": "retried-token",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        ),
    )
    assert auth.load_credentials().token == "retried-token"


def test_failed_profile_commit_removes_new_secret_and_preserves_previous(memory, monkeypatch):
    mock_http(monkeypatch, lambda _: httpx.Response(200, json={"id": 42}))
    auth.login_token("https://school.example", "existing-token")
    metadata = load_profile()
    before = memory.items.copy()

    def fail(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(auth, "save_profile", fail)
    with pytest.raises(OSError):
        auth.login_token("https://school.example", "replacement-token")
    assert load_profile() == metadata
    assert memory.items == before
    assert auth.load_credentials().token == "existing-token"
