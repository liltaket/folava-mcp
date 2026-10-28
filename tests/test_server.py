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
    assert not failure["complete"] and failure["error"]["code"] == "demo_unavailable"


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
