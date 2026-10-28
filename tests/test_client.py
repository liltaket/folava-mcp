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
        api = _file_api_response(request)
        if api is not None:
            assert request.headers["authorization"] == "Bearer secret"
            return api
        assert "authorization" not in request.headers
        if request.url.host == "bucket.s3.amazonaws.com":
            return httpx.Response(
                302,
                headers={
                    "location": "https://bucket.s3.eu-north-1.amazonaws.com/object?signature=redirected-private"
                },
            )
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
    assert len(seen) == 4


def test_stream_size_limit_without_content_length():
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"123"
            yield b"456"

    def handler(request):
        api = _file_api_response(request)
        return api if api is not None else httpx.Response(200, stream=Stream())

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
        api = _file_api_response(request, size=10)
        return (
            api
            if api is not None
            else httpx.Response(206, content=b"abc", headers={"content-range": "bytes 0-2/10"})
        )

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
        api = _file_api_response(request)
        return api if api is not None else httpx.Response(200, content=b"file")

    async def scenario():
        async with CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        ) as client:
            await client.file("1")

    with caplog.at_level(logging.INFO, logger="httpx"):
        run(scenario())
    assert "private" not in caplog.text


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


async def test_file_redirect_back_to_canvas_is_rejected_before_network():
    seen = []

    def handler(request):
        seen.append(request)
        api = _file_api_response(request)
        if api is not None:
            return api
        assert "authorization" not in request.headers
        return httpx.Response(
            302, headers={"location": "https://canvas.example:443/files/1/download?preview=1"}
        )

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(CanvasError) as error:
            await client.file("1")
        assert error.value.code == "policy"
    assert len(seen) == 3


@pytest.mark.parametrize(
    "location",
    [
        "http://bucket.s3.amazonaws.com/object",
        "https://u:p@bucket.s3.amazonaws.com/object",
        "https://bucket.s3.amazonaws.com:8443/object",
        "https://canvas.example/api/v1/conversations/1",
        "https://separate-canvas-filehost.example/files/1/download",
        "https://bucket.s3-website-us-east-1.amazonaws.com/object",
    ],
)
async def test_file_redirect_boundary_checks_before_next_network_request(location):
    seen = []

    def handler(request):
        seen.append(request)
        api = _file_api_response(request)
        return api if api is not None else httpx.Response(302, headers={"location": location})

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(CanvasError) as error:
            await client.file("1")
        assert error.value.code == "policy"
    assert len(seen) == 3


@pytest.mark.parametrize(
    "pointer",
    [
        "https://canvas.example/files/1/download?preview=1",
        "https://canvas.example:443/files/1/download?preview=0&preview%5B%5D=false",
        "https://separate-canvas-filehost.example/files/1/download?sf_verifier=private",
        "https://bucket.s3.amazonaws.com/files/1/download?preview=1",
    ],
)
async def test_canvas_download_and_preview_fallbacks_are_never_requested(pointer):
    seen = []

    def handler(request):
        seen.append(request)
        api = _file_api_response(request, public_url=pointer)
        if api is None:
            pytest.fail("Canvas file controllers may change progression, even in preview mode")
        return api

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(CanvasError) as error:
            await client.file("1")
        assert error.value.code == "policy"
    assert len(seen) == 2


@pytest.mark.parametrize(
    "operation,path",
    [
        ("assignment", {"course_id": "1", "assignment_id": "2"}),
        ("module_item", {"course_id": "1", "module_id": "2", "item_id": "3"}),
        ("quiz_submissions", {"course_id": "1", "quiz_id": "2"}),
        ("quiz_submission", {"course_id": "1", "quiz_id": "2", "submission_id": "3"}),
    ],
)
async def test_upstream_mutating_reads_fail_before_network(operation, path):
    def forbidden(request):
        pytest.fail("An upstream mutating GET must never reach the network")

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(forbidden)
    ) as client:
        with pytest.raises(CanvasError) as error:
            await client.read(operation, path)
        assert error.value.code == "policy"


async def test_safe_assignment_collection_can_filter_one_assignment_without_detail_get():
    def handler(request):
        assert request.url.path == "/api/v1/courses/1/assignments"
        assert request.url.params.get_list("assignment_ids[]") == ["2"]
        assert request.url.params.get_list("include[]") == ["submission"]
        return httpx.Response(200, json=[{"id": 2, "description": "Safe collection instructions"}])

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        result = await client.read(
            "assignments",
            {"course_id": "1"},
            {"assignment_ids[]": ["2"], "include[]": ["submission"]},
        )
    assert result["complete"] and result["data"][0]["id"] == 2


@pytest.mark.parametrize("include", ["read_state", "%72ead_state", "read_status"])
async def test_submission_pagination_mutating_include_rejected_before_second_network_call(include):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json=[],
            headers={
                "link": "<https://canvas.example/api/v1/courses/1/assignments/2/submissions?include%5B%5D="
                + include
                + '>; rel="next"'
            },
        )

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(CanvasError) as error:
            await client.read("submissions", {"course_id": "1", "assignment_id": "2"}, max_pages=2)
        assert error.value.code == "policy"
    assert len(seen) == 1


def _file_api_response(
    request, *, public_url="https://bucket.s3.amazonaws.com/object?signature=private", size=None
):
    if request.url.path == "/api/v1/files/1/public_url":
        assert not request.url.query
        return httpx.Response(200, json={"public_url": public_url})
    if request.url.path == "/api/v1/files/1":
        return httpx.Response(
            200,
            json={
                "id": 1,
                "filename": "notes.txt",
                "size": size,
                "url": "https://canvas.example/files/1/download?unsafe_progression=1",
            },
        )
    return None


@pytest.mark.parametrize(
    "operation,path",
    [
        ("page", {"course_id": "1", "page_url": "intro"}),
        ("front_page", {"course_id": "1"}),
        ("group_page", {"group_id": "1", "page_url": "intro"}),
        ("group_front_page", {"group_id": "1"}),
        ("page_revision", {"course_id": "1", "page_url": "intro", "revision_id": "2"}),
        ("group_page_revision", {"group_id": "1", "page_url": "intro", "revision_id": "2"}),
    ],
)
async def test_excluded_page_reads_fail_before_network(operation, path):
    def forbidden(request):
        pytest.fail("Excluded page actions must never reach Canvas")

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(forbidden)
    ) as client:
        with pytest.raises(CanvasError) as error:
            await client.read(operation, path)
        assert error.value.code == "policy"


@pytest.mark.parametrize(
    "operation,path,expected_url",
    [
        ("pages", {"course_id": "1"}, "/api/v1/courses/1/pages"),
        ("group_pages", {"group_id": "2"}, "/api/v1/groups/2/pages"),
    ],
)
async def test_page_bodies_use_only_collection_route(operation, path, expected_url):
    def handler(request):
        assert request.url.path == expected_url
        assert request.url.params.get_list("include[]") == ["body"]
        return httpx.Response(200, json=[{"url": "intro", "body": "<p>Course information</p>"}])

    async with CanvasClient(
        "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        result = await client.read(operation, path, {"include[]": ["body"]})
    assert result["complete"] and result["data"][0]["body"] == "<p>Course information</p>"
