import pytest

from folava_mcp.client import CanvasError
from folava_mcp.demo import DemoClient


async def test_demo_rejects_unsafe_queries_and_missing_resources():
    async with DemoClient() as client:
        with pytest.raises(CanvasError) as error:
            await client.read("courses", query={"as_user_id": "42"})
        assert error.value.code == "policy"
        with pytest.raises(CanvasError) as error:
            await client.read("assignments", {"course_id": "999"})
        assert error.value.code == "not_found"


async def test_demo_file_obeys_id_and_byte_limit():
    async with DemoClient() as client:
        with pytest.raises(CanvasError) as error:
            await client.file("601", max_bytes=1)
        assert error.value.code == "too_large"
        with pytest.raises(CanvasError) as error:
            await client.file("602")
        assert error.value.code == "not_found"


async def test_demo_calendar_types_and_date_window():
    async with DemoClient() as client:
        events = await client.read("calendar_events", query={"type": "event"})
        work = await client.read("calendar_events", query={"type": "assignment"})
        assert events["data"][0]["id"] != work["data"][0]["id"]
        outside = await client.read("planner_items", query={"start_date": "2027-01-01"})
        assert outside["data"] == []


async def test_demo_supports_safe_page_body_collection_and_assignment_filter_alternatives():
    async with DemoClient() as client:
        path = {"course_id": "101"}
        pages = await client.read("pages", path)
        assert "body" not in pages["data"][0]
        bodies = await client.read("pages", path, {"include[]": ["body"]})
        assert "careful notes" in bodies["data"][0]["body"]
        selected = await client.read("assignments", path, {"assignment_ids[]": ["201"]})
        missing = await client.read("assignments", path, {"assignment_ids[]": ["999"]})
        assert len(selected["data"]) == 1 and missing["data"] == []


def test_output_clipping_has_a_depth_budget():
    from folava_mcp.server import _bounded

    value = {"body": "hello"}
    for _ in range(120):
        value = {"nested": value}
    output = _bounded({"data": value, "complete": True})
    assert output["content_truncated"] and not output["complete"]
