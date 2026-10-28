"""Small synthetic workspace for trying the protocol without an account."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

DEMO_ORIGIN = "https://canvas.example.edu"


class DemoClient:
    origin = DEMO_ORIGIN

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def read(self, operation, path=None, query=None, *, max_pages=1):
        from folava_mcp.client import CanvasError
        from folava_mcp.policy import PolicyError, operation_path, validate_query

        try:
            op, request_path = operation_path(operation, path)
            safe_query = validate_query(op, query)
            if type(max_pages) is not int or not 1 <= max_pages <= 20:
                raise PolicyError("max_pages must be between 1 and 20.")
        except PolicyError as error:
            raise CanvasError("policy", str(error)) from None
        expected = {
            "course_id": "101",
            "assignment_id": "201",
            "module_id": "401",
            "file_id": "601",
            "page_url": "reading-notes",
            "user_id": "self",
        }
        if any(key in expected and value != expected[key] for key, value in (path or {}).items()):
            raise CanvasError("not_found", "This resource is not in the synthetic workspace.")
        operation = {
            "planner": "planner_items",
            "calendar": "calendar_events",
            "course_files": "files",
            "file_metadata": "file",
        }.get(operation, operation)

        course = {
            "id": 101,
            "name": "Introduction to Environmental Science",
            "course_code": "ENV101",
            "workflow_state": "available",
            "html_url": f"{self.origin}/courses/101",
        }
        assignment = {
            "id": 201,
            "course_id": 101,
            "name": "Field observation report",
            "due_at": "2026-11-05T16:00:00Z",
            "points_possible": 20,
            "description": "<p>Record and discuss three observations.</p>",
            "html_url": f"{self.origin}/courses/101/assignments/201",
        }
        submission = {
            "id": 301,
            "assignment_id": 201,
            "user_id": 11,
            "workflow_state": "submitted",
            "submitted_at": "2026-11-03T10:30:00Z",
            "grade": None,
            "submission_comments": [],
        }
        data = {
            "profile": {"id": 11, "name": "Demo Student", "short_name": "Demo"},
            "courses": [course],
            "course": course,
            "assignments": [assignment],
            "assignment": assignment,
            "submission": submission,
            "modules": [{"id": 401, "name": "Week 1 · Observe", "position": 1}],
            "module_items": [
                {
                    "id": 402,
                    "title": "Reading notes",
                    "type": "Page",
                    "page_url": "reading-notes",
                    "position": 1,
                }
            ],
            "pages": [{"page_id": 501, "url": "reading-notes", "title": "Reading notes"}],
            "page": {
                "page_id": 501,
                "url": "reading-notes",
                "title": "Reading notes",
                "body": "<p>Observation begins with careful notes.</p>",
            },
            "files": [
                {
                    "id": 601,
                    "display_name": "field-guide.txt",
                    "size": 66,
                    "content-type": "text/plain",
                }
            ],
            "file": {
                "id": 601,
                "display_name": "field-guide.txt",
                "size": 66,
                "content-type": "text/plain",
            },
            "planner_items": [
                {
                    "context_type": "Course",
                    "course_id": 101,
                    "plannable_type": "assignment",
                    "plannable": assignment,
                    "plannable_date": assignment["due_at"],
                }
            ],
            "calendar_events": [
                {
                    "id": 701,
                    "title": "Fieldwork seminar",
                    "start_at": "2026-11-02T09:00:00Z",
                    "end_at": "2026-11-02T10:00:00Z",
                    "context_code": "course_101",
                }
            ],
            "announcements": [
                {
                    "id": 801,
                    "title": "Bring your field notebook",
                    "message": "<p>We meet by the library at 09:00.</p>",
                }
            ],
        }
        if operation not in data:
            raise CanvasError("demo_unavailable", "This operation is not in the synthetic demo.")
        result = data[operation]
        if operation == "calendar_events" and safe_query.get("type") == "assignment":
            result = [
                {
                    **assignment,
                    "id": "assignment_201",
                    "start_at": assignment["due_at"],
                    "context_code": "course_101",
                }
            ]
        if isinstance(result, list):
            if (
                safe_query.get("context_codes[]")
                and "course_101" not in safe_query["context_codes[]"]
            ):
                result = []
            for bound, after in (("start_date", True), ("end_date", False)):
                if bound in safe_query:
                    day = safe_query[bound][:10]

                    def in_window(item, day=day, after=after):
                        date = item.get("plannable_date", item.get("start_at", ""))[:10]
                        return not date or (date >= day if after else date <= day)

                    result = [item for item in result if in_window(item)]
            if "search_term" in safe_query:
                term = safe_query["search_term"].casefold()
                result = [
                    item
                    for item in result
                    if term
                    in str(
                        item.get("name", item.get("title", item.get("display_name", "")))
                    ).casefold()
                ]
            page = safe_query.get("page", "1")
            if not page.isascii() or not page.isdecimal() or int(page) < 1:
                raise CanvasError("policy", "Demo page must be a positive integer.")
            if int(page) > 1:
                result = []
        return {
            "data": result,
            "source_url": self.origin + request_path,
            "fetched_at": datetime.now(UTC).isoformat(),
            "pages": 1,
            "complete": True,
            "demo": True,
        }

    async def file(self, file_id, *, max_bytes=5_000_000):
        from folava_mcp.client import CanvasError
        from folava_mcp.policy import PolicyError, operation_path

        try:
            operation_path("file", {"file_id": file_id})
        except PolicyError as error:
            raise CanvasError("policy", str(error)) from None
        if file_id != "601":
            raise CanvasError("not_found", "This file is not in the synthetic workspace.")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 20_000_000:
            raise CanvasError("policy", "Invalid file byte limit.")
        content = b"Field guide\nObserve carefully. Record time, place and conditions.\n"
        if len(content) > max_bytes:
            raise CanvasError("too_large", "File exceeds the configured byte limit.")
        return {
            "id": str(file_id),
            "filename": "field-guide.txt",
            "mime_type": "text/plain",
            "size": len(content),
            "sha256": sha256(content).hexdigest(),
            "text": content.decode(),
            "demo": True,
        }
