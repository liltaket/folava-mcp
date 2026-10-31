import os
import sys
from pathlib import Path

import pytest
from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from folava_mcp.server import Workspace, _bounded


async def test_demo_workflows():
    workspace = Workspace("default", True)
    courses = await workspace.read("courses")
    assert courses["demo"] and courses["complete"]
    assert courses["data"][0]["id"] == 101
    failure = await workspace.read("unsupported")
    assert not failure["complete"] and failure["error"]["code"] == "policy"


def test_output_clipping_never_claims_complete():
    output = _bounded({"data": [{"id": 1, "body": "a" * 100_000}], "complete": True})
    assert output["content_truncated"]
    assert not output["complete"]
    assert output["data"][0]["id"] == 1


@pytest.mark.asyncio
async def test_real_stdio_initialize_list_call_and_validation(tmp_path):
    # Exercise the real process + official SDK. No token or institution required.
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "FOLAVA_CONFIG_DIR": str(tmp_path)}
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "folava_mcp", "serve", "--demo"], env=env
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            initialized = await client.initialize()
            assert initialized.server_info.name == "Folava MCP"
            tools = (await client.list_tools()).tools
            assert {
                "canvas_read",
                "canvas_courses",
                "canvas_submission",
                "canvas_agenda",
                "canvas_file",
                "canvas_file_text",
                "canvas_page",
                "canvas_discover",
            } <= {tool.name for tool in tools}
            assert all(tool.annotations.read_only_hint for tool in tools)
            result = await client.call_tool("canvas_courses")
            assert not result.is_error
            assert result.structured_content["data"][0]["id"] == 101
            discovered = await client.call_tool("canvas_discover", {"search": "submission"})
            assert discovered.structured_content["count"] >= 1
            invalid = await client.call_tool(
                "canvas_read", {"operation": "courses", "max_pages": 500}
            )
            assert invalid.is_error
            agenda = await client.call_tool(
                "canvas_agenda",
                {
                    "start_date": "2026-11-01",
                    "end_date": "2026-11-10",
                    "course_ids": [str(i) for i in range(1, 12)],
                },
            )
            assert len(agenda.structured_content["sources"]) == 5
            attachment = await client.call_tool("canvas_file", {"file_id": "601"})
            assert "Observe carefully" in attachment.structured_content["text"]
            text = await client.call_tool("canvas_file_text", {"file_id": "601"})
            assert text.structured_content["complete"]
            assert "Observe carefully" in text.structured_content["text"]
            page = await client.call_tool(
                "canvas_page", {"course_id": "101", "page_url": "reading-notes"}
            )
            assert page.structured_content["complete"]
            assert "Observation begins" in page.structured_content["data"]["body"]
            resources = await client.list_resources()
            assert any(str(item.uri) == "folava://guide" for item in resources.resources)


def test_aggregate_output_cap_for_wide_and_nested_objects():
    import json

    for result in [
        {"data": {str(i): "ö" * 19000 for i in range(20)}, "complete": True},
        {
            "sources": {
                str(i): {"data": [{"body": "a" * 19000} for _ in range(3)], "complete": True}
                for i in range(10)
            },
            "complete": True,
        },
    ]:
        output = _bounded(result)
        assert len(json.dumps(output, ensure_ascii=False).encode()) < 70_000
        assert output["content_truncated"] and not output["complete"]


async def test_agenda_uses_one_client_and_preserves_partial_failures():
    from folava_mcp.client import CanvasError
    from folava_mcp.server import create_server

    instances, calls = [], []

    class Client:
        async def __aenter__(self):
            instances.append(self)
            return self

        async def __aexit__(self, *args):
            pass

        async def read(self, operation, path=None, query=None, **kwargs):
            calls.append((operation, query))
            if operation == "calendar_events" and query["type"] == "event":
                raise CanvasError("forbidden", "Calendar access is not allowed.")
            return {"data": [], "complete": True}

    server = create_server(client_factory=Client)
    result = await server.call_tool(
        "canvas_agenda",
        {"start_date": "2026-11-01", "end_date": "2026-11-07", "course_ids": ["101"]},
    )
    output = result.structured_content
    assert len(instances) == 1 and len(calls) == 3
    assert not output["complete"]
    assert output["sources"]["calendar_0_event"]["error"]["code"] == "forbidden"
    assert output["sources"]["calendar_0_assignment"]["complete"]


async def test_agenda_deadline_cancels_and_reports_partial_sources(monkeypatch):
    import asyncio

    from folava_mcp import server as module

    closed = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            closed.append(True)

        async def read(self, operation, *args, **kwargs):
            if operation != "planner_items":
                await asyncio.sleep(10)
            return {"data": [], "complete": True}

    monkeypatch.setattr(module, "AGENDA_TIMEOUT", 0.02)
    result = await module.create_server(client_factory=Client).call_tool(
        "canvas_agenda",
        {"start_date": "2026-11-01", "end_date": "2026-11-07", "course_ids": ["101"]},
    )
    output = result.structured_content
    assert not output["complete"] and output["sources"]["planner"]["complete"]
    assert output["sources"]["remaining"]["error"]["code"] == "timeout"
    assert closed == [True]


async def test_agenda_rejects_non_ascii_ids_and_overlong_ranges_before_connecting():
    from folava_mcp.server import create_server

    def forbidden_factory():
        raise AssertionError("Invalid agenda must not connect")

    server = create_server(client_factory=forbidden_factory)
    for arguments in (
        {"start_date": "2026-01-01T00:00:00Z", "end_date": "2027-01-02T01:00:00Z"},
        {"start_date": "2026-11-01", "end_date": "2026-11-07", "course_ids": ["١٠١"]},
    ):
        result = await server.call_tool("canvas_agenda", arguments)
        assert result.structured_content["error"]["code"] == "input"
