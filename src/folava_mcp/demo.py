"""Small synthetic workspace for trying the protocol without an account."""

from __future__ import annotations

import base64
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
        return {
            "data": data[operation],
            "source_url": self.origin,
            "fetched_at": datetime.now(UTC).isoformat(),
            "pages": 1,
            "complete": True,
            "demo": True,
        }

    async def file(self, file_id, *, max_bytes=5_000_000):
        content = b"Field guide\nObserve carefully. Record time, place and conditions.\n"
        return {
            "id": str(file_id),
            "filename": "field-guide.txt",
            "mime_type": "text/plain",
            "size": len(content),
            "sha256": sha256(content).hexdigest(),
            "text": content.decode(),
            "content_base64": base64.b64encode(content).decode(),
            "demo": True,
        }
