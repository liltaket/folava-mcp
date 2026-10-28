import pytest

from folava_mcp.catalog import OPERATIONS
from folava_mcp.policy import (
    PolicyError,
    build_url,
    operation_path,
    validate_continuation,
    validate_origin,
    validate_query,
)


@pytest.mark.parametrize(
    "origin",
    [
        "http://canvas.example",
        "https://u:p@canvas.example",
        "https://canvas.example/api/v1",
        "https://canvas.example?token=x",
        "https://canvas.example:8443",
        "https://canvas.example/#x",
        "https://canvas.example\\@evil.example",
    ],
)
def test_invalid_origins(origin):
    with pytest.raises(PolicyError):
        validate_origin(origin)


def test_origin_canonicalization():
    assert validate_origin("https://Canvas.Example:443/") == "https://canvas.example"


@pytest.mark.parametrize(
    "query",
    [
        {"access_token": "secret"},
        {"as_user_id": 1},
        {"_method": "POST"},
        {"method": "DELETE"},
        {"include[0]": "read_status"},
        {"include[]": ["submission_comments", "read_status"]},
        {"include[]": "submission_history,read_status"},
        {"include[]": "READ_STATUS"},
    ],
)
def test_read_side_effect_and_override_parameters_blocked(query):
    with pytest.raises(PolicyError):
        validate_query(OPERATIONS["submission"], query)


@pytest.mark.parametrize("value", [True, "true", "1", 1, [False, True]])
def test_conversation_cannot_mark_read(value):
    with pytest.raises(PolicyError):
        validate_query(OPERATIONS["conversation"], {"auto_mark_as_read": value})


def test_conversation_always_forces_no_read():
    assert validate_query(OPERATIONS["conversation"], {}) == {"auto_mark_as_read": "false"}


@pytest.mark.parametrize(
    "path",
    [
        {"course_id": "../1"},
        {"course_id": "%2F1"},
        {"course_id": "1?method=POST"},
        {"course_id": "1", "url": "https://evil.example"},
        {"course_id": "settings"},
        {},
    ],
)
def test_path_injection_or_static_action_rejected(path):
    with pytest.raises(PolicyError):
        operation_path("assignments", path)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/api/v1/courses?page=2",
        "https://canvas.example/api/v1/conversations/1",
        "https://canvas.example/api/v1/courses?as_user_id=3",
        "https://canvas.example/api/v1/courses?page=1&page=2",
        "https://canvas.example/api/v1/courses#include",
        "https://canvas.example/api/v1/courses?include%5B%5D=read_status",
    ],
)
def test_pagination_boundary(url):
    with pytest.raises(PolicyError):
        validate_continuation(
            url, "https://canvas.example", OPERATIONS["courses"], "/api/v1/courses"
        )


def test_arrays_and_pagination_roundtrip():
    op = OPERATIONS["courses"]
    url = build_url(
        "https://canvas.example",
        op,
        op.path,
        {"include[]": ["term", "syllabus_body"], "per_page": 50},
    )
    assert validate_continuation(url, "https://canvas.example", op, op.path) == url


def test_calendar_does_not_silently_drop_extra_contexts():
    with pytest.raises(PolicyError):
        validate_query(
            OPERATIONS["calendar_events"], {"context_codes[]": [f"course_{i}" for i in range(11)]}
        )


def test_swedish_page_slug_encoded_as_one_path_segment():
    _, path = operation_path("page", {"course_id": "1", "page_url": "övningar-för-studenter"})
    assert path == "/api/v1/courses/1/pages/%C3%B6vningar-f%C3%B6r-studenter"
    url = "https://canvas.example" + path + "?page=2"
    assert validate_continuation(url, "https://canvas.example", OPERATIONS["page"], path) == url


def test_international_domain_is_canonical_ascii_origin():
    assert validate_origin("https://lärosäte.example/") == "https://xn--lroste-buad.example"


@pytest.mark.parametrize("path", [[], ["course_id"], "course_id", 7])
def test_non_object_path_is_rejected_consistently(path):
    with pytest.raises(PolicyError):
        operation_path("courses", path)


@pytest.mark.parametrize("query", [[], "", 0, False])
def test_falsey_non_object_query_is_rejected_consistently(query):
    with pytest.raises(PolicyError):
        validate_query(OPERATIONS["courses"], query)
