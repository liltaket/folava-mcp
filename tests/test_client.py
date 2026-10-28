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
