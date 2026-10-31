import httpx
import pytest

from folava_mcp.client import CanvasClient, CanvasError
from folava_mcp.pages import read_page
from folava_mcp.server import create_server


async def test_page_selection_uses_only_paginated_collection_and_clips_after_selecting():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.path == "/api/v1/courses/1/pages"
        assert request.url.params["include[]"] == "body"
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[{"url": "övningar", "body": "Read this page"}])
        return httpx.Response(
            200,
            json=[{"url": "other", "body": "x" * 100_000}],
            headers={
                "Link": "<https://canvas.example/api/v1/courses/1/pages?"
                'page=2&include%5B%5D=body>; rel="next"'
            },
        )

    server = create_server(
        client_factory=lambda: CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        )
    )
    result = (
        await server.call_tool(
            "canvas_page",
            {
                "course_id": "1",
                "page_url": "övningar",
            },
        )
    ).structured_content
    assert result["complete"] and result["data"]["body"] == "Read this page"
    assert len(seen) == 2 and result["pages"] == 2
    assert "content_truncated" not in result


@pytest.mark.parametrize("complete, code", [(True, "not_found"), (False, "page_search_incomplete")])
async def test_missing_page_distinguishes_incomplete_collection(complete, code):
    class Client:
        async def read(self, *args, **kwargs):
            return {"data": [], "complete": complete}

    with pytest.raises(CanvasError) as error:
        await read_page(Client(), "1", "missing", 1)
    assert error.value.code == code


async def test_body_omission_and_found_page_in_partial_collection():
    class Client:
        async def read(self, *args, **kwargs):
            return {"data": [{"url": "intro", **self.body}], "complete": False}

    client = Client()
    client.body = {}
    result = await read_page(client, "1", "intro", 1)
    assert not result["complete"] and result["error"]["code"] == "page_body_unavailable"
    client.body = {"body": ""}
    result = await read_page(client, "1", "intro", 1)
    assert result["complete"] and not result["collection_complete"]


@pytest.mark.parametrize("slug", ["../intro", "https://canvas.example/courses/1/pages/intro", ""])
async def test_invalid_page_identifiers_never_reach_network(slug):
    class Client:
        async def read(self, *args, **kwargs):
            pytest.fail("Invalid input must not reach Canvas")

    with pytest.raises(CanvasError) as error:
        await read_page(Client(), "1", slug, 1)
    assert error.value.code == "policy"
