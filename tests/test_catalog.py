import pytest

from folava_mcp.catalog import OPERATIONS, discover
from folava_mcp.policy import PolicyError, operation_path


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
            action in op.path for action in ("mark_read", "take_quiz", "reset", "session_token")
        )
        assert "access_token" not in op.query_keys


def test_progression_and_quiz_mutation_routes_are_not_discoverable_or_reachable():
    excluded = {"assignment", "module_item", "quiz_submissions", "quiz_submission"}
    assert not excluded.intersection(entry["id"] for entry in discover())
    for operation in excluded:
        with pytest.raises(PolicyError):
            operation_path(operation, {})
    assert "assignment_ids[]" in OPERATIONS["assignments"].query_keys
    assert "module_items" in OPERATIONS


def test_storage_pointer_is_exact_audited_api_route_without_extra_context_parameters():
    operation = OPERATIONS["file_download_url"]
    assert operation.path == "/api/v1/files/{file_id}/public_url"
    assert operation.required_path == ["file_id"]
    assert operation.query_keys == ()


@pytest.mark.parametrize(
    "operation",
    [
        "page",
        "front_page",
        "group_page",
        "group_front_page",
        "page_revision",
        "group_page_revision",
    ],
)
def test_excluded_page_detail_and_revision_operations_fail_closed(operation):
    assert operation not in {entry["id"] for entry in discover()}
    with pytest.raises(PolicyError):
        operation_path(operation, {})


def test_page_content_collection_alternatives_and_revision_metadata_remain_available():
    assert {"pages", "group_pages", "page_revisions", "group_page_revisions"} <= OPERATIONS.keys()
    for operation in ("pages", "group_pages"):
        descriptor = OPERATIONS[operation]
        assert "include[]" in descriptor.query_keys
        assert "include[]=body" in descriptor.description
