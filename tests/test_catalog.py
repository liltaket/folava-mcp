from folava_mcp.catalog import OPERATIONS, discover
from folava_mcp.policy import operation_path


def test_catalog_describes_supported_workflows():
    required = {
        "courses",
        "assignments",
        "submission",
        "modules",
        "module_items",
        "planner_items",
        "calendar_events",
        "profile",
        "files",
        "file",
        "pages",
        "page",
        "announcements",
    }
    assert required <= OPERATIONS.keys()
    assert len(OPERATIONS) >= 80
    assert all(op.path.startswith("/api/v1/") for op in OPERATIONS.values())
    assert discover("submission feedback")
    assert not discover("unobtainium")


def test_all_templates_construct_without_action_routes():
    for op in OPERATIONS.values():
        values = {key: "1" for key in op.required_path}
        assert operation_path(op.id, values)[1].startswith("/api/v1/")
        assert not any(
            action in op.path
            for action in ("mark_read", "take_quiz", "reset", "session_token", "public_url")
        )
        assert "access_token" not in op.query_keys
