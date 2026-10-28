"""Explicit, bounded live Canvas reads. Emits technical summaries, never coursework."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from folava_mcp.client import CanvasClient, CanvasError  # noqa: E402
from folava_mcp.config import read_token_file  # noqa: E402
from folava_mcp.policy import validate_origin  # noqa: E402
from folava_mcp.server import create_server  # noqa: E402


class ReadAudit:
    """Second boundary: no credential lifecycle, Canvas UI or non-GET request."""

    def __init__(self, origin: str, max_requests: int = 40):
        self.host = urlsplit(validate_origin(origin)).hostname
        self.max_requests = max_requests
        self.methods = Counter()
        self.statuses = Counter()

    def wrap(self, delegate):
        audit = self

        class Transport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                if request.method != "GET":
                    raise CanvasError("audit", "Live validation refuses every non-GET request.")
                host = request.extensions.get("sni_hostname", request.url.host)
                if isinstance(host, bytes):
                    host = host.decode("ascii")
                if host == audit.host and not request.url.path.startswith("/api/v1/"):
                    raise CanvasError("audit", "Live validation refuses Canvas UI routes.")
                if host != audit.host and "authorization" in request.headers:
                    raise CanvasError("audit", "Live validation refuses cross-origin credentials.")
                if sum(audit.methods.values()) >= audit.max_requests:
                    raise CanvasError("budget", "Live validation request budget reached.")
                audit.methods[request.method] += 1
                response = await delegate.handle_async_request(request)
                audit.statuses[str(response.status_code)] += 1
                return response

            async def aclose(self):
                await delegate.aclose()

        return Transport()


def result_summary(label: str, envelope: dict) -> dict:
    if envelope.get("error"):
        return {"scenario": label, "status": "unavailable", "error_code": envelope["error"]["code"]}
    data = envelope.get("data")
    return {
        "scenario": label,
        "status": "ok",
        "complete": envelope.get("complete", True),
        "shape": "list" if isinstance(data, list) else "object",
        **({"items": len(data)} if isinstance(data, list) else {}),
    }


def compare_progress(before, after) -> dict:
    """Classify observations without emitting resource identifiers or coursework.

    A difference is evidence about two responses, not attribution to a request:
    Canvas may refresh derived progress while serving a list, and people or other
    clients can change state concurrently. Only compare the bounded sample.
    """

    def index(values):
        if not isinstance(values, list):
            return None
        result = {}
        for value in values:
            if not isinstance(value, dict) or "id" not in value:
                return None
            identifier = str(value["id"])
            if identifier in result:
                return None
            requirement = value.get("completion_requirement")
            if requirement is not None and not isinstance(requirement, dict):
                return None
            result[identifier] = requirement
        return result

    earlier, later = index(before), index(after)
    if earlier is None or later is None:
        return {"classification": "unavailable"}
    membership = len(earlier.keys() ^ later.keys())
    completed = metadata = 0
    for identifier in earlier.keys() & later.keys():
        a, b = earlier[identifier], later[identifier]
        if (a or {}).get("completed") != (b or {}).get("completed"):
            completed += 1
        a_meta = {k: v for k, v in a.items() if k != "completed"} if a is not None else None
        b_meta = {k: v for k, v in b.items() if k != "completed"} if b is not None else None
        if a_meta != b_meta:
            metadata += 1
    changed = [
        name
        for name, count in (
            ("membership_changed", membership),
            ("completed_changed", completed),
            ("requirement_metadata_changed", metadata),
        )
        if count
    ]
    return {
        "classification": "multiple_changes" if len(changed) > 1 else next(iter(changed), "same"),
        "membership_changes": membership,
        "completed_changes": completed,
        "requirement_metadata_changes": metadata,
    }


async def run(
    origin: str, token: str, *, download_small_file: bool = False, max_requests: int = 40
) -> dict:
    origin = validate_origin(origin)
    audit = ReadAudit(origin, max_requests)
    scenarios = []

    def factory():
        client = CanvasClient(origin, token)
        # Keep the production resolver, TLS verification and public-address policy.
        client._transport = audit.wrap(client._transport)
        return client

    async def read(client, label, operation, path=None, query=None):
        try:
            result = await client.read(operation, path, query, max_pages=1)
        except CanvasError as error:
            result = {"error": {"code": error.code}, "complete": False}
        scenarios.append(result_summary(label, result))
        return result.get("data")

    async def tool(server, label, name, arguments):
        result = await server.call_tool(name, arguments)
        envelope = result.structured_content or {"error": {"code": "protocol"}}
        scenarios.append(result_summary(label, envelope))
        return envelope

    try:
        async with asyncio.timeout(180), factory() as client:
            profile = await read(client, "identity", "profile")
            if not isinstance(profile, dict) or profile.get("id") is None:
                return {
                    "scenarios": scenarios,
                    "request_methods": dict(audit.methods),
                    "status_counts": dict(audit.statuses),
                    "personal_payloads_saved": False,
                }
            courses = await read(
                client, "courses", "courses", query={"per_page": 5, "enrollment_state": "active"}
            )
            today = datetime.now(UTC).date()
            dates = {
                "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=7)).isoformat(),
            }
            planner = await read(client, "planner", "planner_items", query={**dates, "per_page": 5})
            planned_course = next(
                (
                    str(item["course_id"])
                    for item in planner or []
                    if item.get("course_id")
                    and re.fullmatch(r"[0-9]{1,20}", str(item["course_id"]))
                ),
                None,
            )
            candidates = [
                item for item in courses or [] if isinstance(item, dict) and item.get("id")
            ]
            candidates.sort(key=lambda item: item.get("workflow_state") != "available")
            if not candidates and not planned_course:
                scenarios.append(
                    {
                        "scenario": "course_workflows",
                        "status": "skipped",
                        "reason": "no accessible course in sample",
                    }
                )
            else:
                course_id = planned_course or str(candidates[0]["id"])
                path = {"course_id": course_id}
                await read(client, "course_metadata", "course", path)
                assignments = await read(
                    client,
                    "assignment_collection",
                    "assignments",
                    path,
                    {"per_page": 5, "include[]": ["submission"]},
                )
                modules = await read(client, "modules", "modules", path, {"per_page": 5})
                items = []
                module_samples = []
                for index, module in enumerate((modules or [])[:3]):
                    module_path = {**path, "module_id": str(module["id"])}
                    sample = await read(
                        client,
                        f"module_items_{index + 1}",
                        "module_items",
                        module_path,
                        {"per_page": 5, "include[]": ["content_details"]},
                    )
                    if isinstance(sample, list):
                        items.extend(sample)
                        module_samples.append((module_path, sample))
                # Never fall back to individual page or revision routes.
                pages = await read(
                    client,
                    "page_collection_with_body",
                    "pages",
                    path,
                    {"per_page": 5, "include[]": ["body"]},
                )
                if assignments:
                    assignment_id = str(assignments[0]["id"])
                    await read(
                        client,
                        "filtered_assignment",
                        "assignments",
                        path,
                        {"assignment_ids[]": [assignment_id], "per_page": 5},
                    )
                    await read(
                        client,
                        "own_submission",
                        "submission",
                        {**path, "assignment_id": assignment_id, "user_id": "self"},
                        {
                            "include[]": [
                                "submission_comments",
                                "submission_history",
                                "rubric_assessment",
                            ]
                        },
                    )
                for kind in ("event", "assignment"):
                    await read(
                        client,
                        "calendar_" + kind,
                        "calendar_events",
                        query={
                            **dates,
                            "type": kind,
                            "context_codes[]": ["course_" + course_id],
                            "per_page": 5,
                        },
                    )
                await read(
                    client,
                    "announcements",
                    "announcements",
                    query={
                        "context_codes[]": ["course_" + course_id],
                        "per_page": 5,
                        "start_date": (today - timedelta(days=14)).isoformat(),
                        "end_date": dates["end_date"],
                    },
                )
                # Extract only numeric file identifiers; never navigate source HTML links.
                file_ids = [
                    str(item["content_id"])
                    for item in items or []
                    if item.get("type") == "File" and item.get("content_id")
                ]
                sources = [item.get("description", "") for item in assignments or []]
                sources.extend(item.get("body", "") for item in pages or [])
                for body in sources:
                    file_ids.extend(re.findall(r"/files/([0-9]+)(?:[/\s?\"']|$)", body or ""))
                if not file_ids:
                    listed_files = await read(
                        client, "file_collection", "files", path, {"per_page": 3}
                    )
                    file_ids.extend(
                        str(item["id"]) for item in listed_files or [] if item.get("id")
                    )
                selected = None
                for candidate in list(dict.fromkeys(file_ids))[:3]:
                    metadata = await read(
                        client, "attachment_metadata", "file", {"file_id": candidate}
                    )
                    if (
                        metadata
                        and metadata.get("size", 200001) <= 200000
                        and not metadata.get("locked_for_user")
                    ):
                        selected = candidate
                        break
                if download_small_file and selected:
                    try:
                        content = await client.file(selected, max_bytes=200000)
                        scenarios.append(
                            {
                                "scenario": "attachment_content",
                                "status": "ok",
                                "bytes": content["size"],
                                "digest_present": bool(content["sha256"]),
                            }
                        )
                    except CanvasError as error:
                        scenarios.append(
                            {
                                "scenario": "attachment_content",
                                "status": "unavailable",
                                "error_code": error.code,
                            }
                        )
                else:
                    scenarios.append(
                        {
                            "scenario": "attachment_content",
                            "status": "skipped",
                            "reason": "No opted-in, accessible attachment below 200 KB in sample.",
                        }
                    )
                server = create_server(client_factory=factory)
                await tool(server, "mcp_courses", "canvas_courses", {})
                await tool(
                    server, "mcp_assignments", "canvas_assignments", {"course_id": course_id}
                )
                await tool(
                    server, "mcp_agenda", "canvas_agenda", {**dates, "course_ids": [course_id]}
                )
                comparisons = []
                for index, (module_path, before) in enumerate(module_samples):
                    after = await read(
                        client,
                        f"module_state_after_{index + 1}",
                        "module_items",
                        module_path,
                        {"per_page": 5, "include[]": ["content_details"]},
                    )

                    comparisons.append(compare_progress(before, after))
                scenarios.append(
                    {
                        "scenario": "sampled_module_progress_observation",
                        "status": "same"
                        if comparisons
                        and all(value["classification"] == "same" for value in comparisons)
                        else "inconclusive",
                        "comparisons": comparisons,
                        "causality_established": False,
                    }
                )
    except TimeoutError:
        scenarios.append(
            {"scenario": "overall_deadline", "status": "unavailable", "error_code": "timeout"}
        )
    return {
        "origin": origin,
        "scenarios": scenarios,
        "request_methods": dict(audit.methods),
        "status_counts": dict(audit.statuses),
        "personal_payloads_saved": False,
        "scope": "one sampled course; not a complete account crawl",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--token-file", type=Path, default=os.environ.get("CANVAS_TOKEN_FILE"))
    parser.add_argument("--download-small-file", action="store_true")
    arguments = parser.parse_args()
    if not arguments.token_file:
        parser.error(
            "Provide a protected --token-file or CANVAS_TOKEN_FILE; never put the token in argv."
        )
    try:
        report = asyncio.run(
            run(
                arguments.origin,
                read_token_file(arguments.token_file),
                download_small_file=arguments.download_small_file,
            )
        )
        print(json.dumps(report, ensure_ascii=False))
        if not report["scenarios"] or report["scenarios"][0]["status"] != "ok":
            sys.exit(1)
    except Exception:
        print(
            json.dumps(
                {
                    "error_code": "validation_failed",
                    "detail": "No credential or upstream payload was printed.",
                }
            )
        )
        sys.exit(1)
        raise SystemExit(1) from None
