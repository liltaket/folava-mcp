import asyncio
import hashlib
import socket

import httpx
import pytest

from folava_mcp.client import CanvasClient, CanvasError, _public_address


def run(coro):
    return asyncio.run(coro)


def test_complete_pagination_and_headers():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer secret"
        if "page=2" in str(request.url):
            return httpx.Response(200, json=[{"id": 2}])
        return httpx.Response(
            200,
            json=[{"id": 1}],
            headers={"LiNk": '<https://canvas.example/api/v1/courses?page=2>; rel="next"'},
        )

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            page = await client.read("courses")
            assert page["complete"] is False
            assert "next_url" in page
            result = await client.read("courses", max_pages=2)
            assert result["data"] == [{"id": 1}, {"id": 2}]
            assert result["pages"] == 2 and result["complete"] is True

    run(scenario())
    assert len(seen) == 3


def test_conversation_override_applies_to_every_page():
    def handler(request):
        assert request.url.params["auto_mark_as_read"] == "false"
        return httpx.Response(200, json={"id": 3})

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            await client.read("conversation", {"conversation_id": "3"})

    run(scenario())


@pytest.mark.parametrize(
    "next_url",
    [
        "https://evil.example/api/v1/courses?page=2",
        "https://canvas.example/api/v1/courses?as_user_id=1",
        "https://canvas.example/api/v1/courses?include%5B%5D=read_status",
    ],
)
def test_hostile_pagination_never_followed(next_url):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=[], headers={"link": f'<{next_url}>; rel="next"'})

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(CanvasError, match="rejected"):
                await client.read("courses", max_pages=2)

    run(scenario())
    assert len(seen) == 1


@pytest.mark.parametrize(
    "status,code", [(401, "auth"), (403, "forbidden"), (404, "not_found"), (400, "upstream")]
)
def test_errors_never_echo_upstream_body(status, code):
    async def scenario():
        async with CanvasClient(
            "https://canvas.example",
            "secret",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, text="secret https://sensitive?token=oops")
            ),
        ) as client:
            with pytest.raises(CanvasError) as error:
                await client.read("courses")
            assert error.value.code == code
            assert "secret" not in str(error.value) and "oops" not in str(error.value)

    run(scenario())


def test_rate_limit_retry_is_bounded():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"retry-after": "0"})

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(CanvasError) as error:
                await client.read("courses")
            assert error.value.retryable and error.value.code == "rate_limit"

    run(scenario())
    assert len(calls) == 3


def test_file_redirects_strip_auth_and_do_not_return_signed_urls():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.startswith("/api/"):
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "filename": "notes.txt",
                    "size": 5,
                    "url": "https://canvas.example/files/1/download",
                },
            )
        if request.url.host == "canvas.example":
            return httpx.Response(
                302, headers={"location": "https://storage.example/notes.txt?signature=private"}
            )
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"hello", headers={"content-type": "text/plain"})

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            result = await client.file("1")
            assert result["text"] == "hello"
            assert result["sha256"] == hashlib.sha256(b"hello").hexdigest()
            assert "private" not in str(result)

    run(scenario())
    assert len(seen) == 3


def test_stream_size_limit_without_content_length():
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"123"
            yield b"456"

    def handler(request):
        if request.url.path.startswith("/api/"):
            return httpx.Response(200, json={"id": 1, "url": "https://storage.example/file"})
        return httpx.Response(200, stream=Stream())

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(CanvasError) as error:
                await client.file("1", max_bytes=5)
            assert error.value.code == "too_large"

    run(scenario())


@pytest.mark.parametrize(
    "ips",
    [
        ["127.0.0.1"],
        ["169.254.169.254"],
        ["::1"],
        ["93.184.216.34", "10.0.0.1"],
        ["::ffff:127.0.0.1"],
    ],
)
def test_dns_rejects_any_private_answer(monkeypatch, ips):
    async def scenario():
        async def fake(*args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))
                for ip in ips
            ]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake)
        with pytest.raises(CanvasError) as error:
            await _public_address("storage.example")
        assert error.value.code == "unsafe_destination"

    run(scenario())


def test_production_pins_ip_and_preserves_host_and_tls_name(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=[])

    async def fake(_):
        return "93.184.216.34"

    async def scenario():
        monkeypatch.setattr("folava_mcp.client._public_address", fake)
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            client._test_transport = (
                False  # exercise production construction, with network still mocked
            )
            await client.read("courses")

    run(scenario())
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "canvas.example"
    assert seen[0].extensions["sni_hostname"] == "canvas.example"


def test_compression_bomb_rejected_before_decoder_allocation():
    import gzip
    import tracemalloc

    compressed = gzip.compress(b"x" * 20_000_000)

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield compressed

    def handler(request):
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, headers={"content-encoding": "gzip"}, stream=Stream())

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            tracemalloc.start()
            try:
                with pytest.raises(CanvasError) as error:
                    await client.read("courses")
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            assert error.value.code == "encoding"
            assert peak < 2_000_000

    run(scenario())


def test_quiz_envelope_pagination_preserves_associated_arrays():
    def handler(request):
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(
            200,
            json={"quiz_submissions": [{"id": page}], "users": [{"id": 10 + page}]},
            headers={}
            if page == 2
            else {
                "link": (
                    "<https://canvas.example/api/v1/courses/1/quizzes/2/"
                    'submissions?page=2>; rel="next"'
                )
            },
        )

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            first = await client.read("quiz_submissions", {"course_id": "1", "quiz_id": "2"})
            assert not first["complete"]
            result = await client.read(
                "quiz_submissions", {"course_id": "1", "quiz_id": "2"}, max_pages=2
            )
            assert result["complete"]
            assert result["data"]["quiz_submissions"] == [{"id": 1}, {"id": 2}]
            assert len(result["data"]["users"]) == 2

    run(scenario())


@pytest.mark.parametrize(
    "body", [b"[" * 2000 + b"0" + b"]" * 2000, b"[NaN]", b"[Infinity]", b"[-Infinity]", b"[1e9999]"]
)
def test_malformed_or_excessively_nested_json_is_safe(body):
    async def scenario():
        async with CanvasClient(
            "https://canvas.example",
            "secret",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body)),
        ) as client:
            with pytest.raises(CanvasError) as error:
                await client.read("courses")
            assert error.value.code == "upstream"

    run(scenario())


def test_link_quoted_comma_and_semicolon_does_not_hide_next_page():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[{"id": 2}])
        return httpx.Response(
            200,
            json=[{"id": 1}],
            headers={
                "link": (
                    "<https://canvas.example/api/v1/courses?page=2>; "
                    'title="Read, then; continue"; rel="next"'
                )
            },
        )

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            result = await client.read("courses", max_pages=2)
            assert result["data"] == [{"id": 1}, {"id": 2}]
            assert result["complete"]

    run(scenario())
    assert len(seen) == 2


@pytest.mark.parametrize(
    "header",
    [
        '<https://canvas.example/api/v1/courses?page=2>; rel="next',
        '<https://canvas.example/api/v1/courses?page=2; rel="next"',
        '<https://canvas.example/api/v1/courses?page=2>; rel="next", garbage',
        '<https://canvas.example/api/v1/courses?page=2>; rel="next"; rel="previous"',
    ],
)
def test_malformed_pagination_never_silently_claims_complete(header):
    async def scenario():
        async with CanvasClient(
            "https://canvas.example",
            "secret",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=[], headers={"link": header})
            ),
        ) as client:
            with pytest.raises(CanvasError) as error:
                await client.read("courses")
            assert error.value.code == "pagination"

    run(scenario())


@pytest.mark.parametrize("response", [{"quiz_submissions": [], "users": "invalid"}, {"users": []}])
def test_quiz_envelope_validated_on_every_page(response):
    async def scenario():
        async with CanvasClient(
            "https://canvas.example",
            "secret",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response)),
        ) as client:
            with pytest.raises(CanvasError):
                await client.read("quiz_submissions", {"course_id": "1", "quiz_id": "2"})

    run(scenario())


@pytest.mark.parametrize(
    "ip", ["224.0.0.1", "ff02::1", "2002:7f00:1::", "2001:0:4136:e378:8000:63bf:3fff:fdd2"]
)
def test_dns_rejects_multicast_and_ipv6_transition_destinations(monkeypatch, ip):
    async def scenario():
        async def fake(*args, **kwargs):
            return [(socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake)
        with pytest.raises(CanvasError) as error:
            await _public_address("storage.example")
        assert error.value.code == "unsafe_destination"

    run(scenario())


def test_file_partial_content_is_not_reported_as_complete():
    def handler(request):
        if request.url.path.startswith("/api/"):
            return httpx.Response(
                200, json={"id": 1, "size": 10, "url": "https://storage.example/file"}
            )
        return httpx.Response(206, content=b"abc", headers={"content-range": "bytes 0-2/10"})

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(CanvasError) as error:
                await client.file("1")
            assert error.value.code == "upstream"

    run(scenario())


def test_httpx_info_logs_never_expose_file_capability_urls(caplog):
    import logging

    def handler(request):
        if request.url.path.startswith("/api/"):
            return httpx.Response(
                200,
                json={"id": 1, "url": "https://storage.example/file?signature=secret-capability"},
            )
        return httpx.Response(200, content=b"file")

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            await client.file("1")

    with caplog.at_level(logging.INFO, logger="httpx"):
        run(scenario())
    assert "secret-capability" not in caplog.text


async def test_cancellation_closes_stream_and_releases_request_lock():
    started, cancelled = asyncio.Event(), asyncio.Event()

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            started.set()
            await asyncio.Event().wait()
            yield b"[]"

        async def aclose(self):
            cancelled.set()

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return (
            httpx.Response(200, stream=SlowStream()) if calls == 1 else httpx.Response(200, json=[])
        )

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        task = asyncio.create_task(client.read("courses"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
        result = await asyncio.wait_for(client.read("courses"), 1)
        assert result["complete"]


async def test_whole_request_deadline_interrupts_stalled_body(monkeypatch):
    real_timeout = asyncio.timeout
    monkeypatch.setattr("folava_mcp.client.asyncio.timeout", lambda _: real_timeout(0.01))
    closed = False

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.Event().wait()
            yield b"[]"

        async def aclose(self):
            nonlocal closed
            closed = True

    async with CanvasClient(
        "https://canvas.example",
        "secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Stream())),
    ) as client:
        with pytest.raises(CanvasError) as error:
            await client.read("courses")
        assert error.value.code == "timeout" and error.value.retryable
        assert closed


async def test_retry_after_and_transport_timeouts_are_bounded(monkeypatch):
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("folava_mcp.client.asyncio.sleep", sleep)
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        assert request.extensions["timeout"] == {"connect": 20, "read": 20, "write": 20, "pool": 20}
        if calls == 1:
            raise httpx.ReadError("private URL credential")
        if calls == 2:
            return httpx.Response(503, headers={"retry-after": "99999"})
        return httpx.Response(200, json=[])

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        result = await client.read("courses")
        assert result["complete"]
    assert calls == 3 and delays == [0.25, 2.0]


async def test_json_complexity_rejected_before_parse_allocation():
    body = b"[" + b"0," * 300_000 + b"0]"
    async with CanvasClient(
        "https://canvas.example",
        "secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body)),
    ) as client:
        with pytest.raises(CanvasError) as error:
            await client.read("courses")
        assert error.value.code == "too_large"


async def test_file_redirect_revalidation_and_credentials_stay_stripped_on_return():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.startswith("/api/"):
            return httpx.Response(
                200, json={"id": 1, "url": "https://canvas.example/files/1/download"}
            )
        if request.url.host == "storage.example":
            assert "authorization" not in request.headers
            return httpx.Response(
                302, headers={"location": "https://canvas.example/files/1/download?returned=1"}
            )
        if "returned" in request.url.params:
            assert "authorization" not in request.headers
            assert "cookie" not in request.headers
            return httpx.Response(200, content=b"ok")
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            302,
            headers={
                "location": "https://storage.example/file",
                "set-cookie": "session=should-not-persist; Secure",
            },
        )

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        result = await client.file("1")
    assert result["size"] == 2 and len(seen) == 4


@pytest.mark.parametrize(
    "location",
    [
        "http://storage.example/file",
        "https://u:p@storage.example/file",
        "https://storage.example:8443/file",
        "https://canvas.example/api/v1/conversations/1",
    ],
)
async def test_file_redirect_boundary_checks_before_next_network_request(location):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.startswith("/api/"):
            return httpx.Response(
                200, json={"id": 1, "url": "https://canvas.example/files/1/download"}
            )
        return httpx.Response(302, headers={"location": location})

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(CanvasError):
            await client.file("1")
    assert len(requests) == 2
