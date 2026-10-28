"""Fail-closed URL and query policy shared by first pages and continuations."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from .catalog import OPERATIONS, Operation


class PolicyError(ValueError):
    """A request was rejected before contacting Canvas."""


def validate_origin(value: str) -> str:
    try:
        if not isinstance(value, str):
            raise PolicyError("Canvas origin must be an HTTPS origin.")
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
            or url.port not in (None, 443)
            or "\\" in value
            or any(ord(char) < 33 for char in value)
        ):
            raise PolicyError("Canvas origin must be an HTTPS origin with no path or credentials.")
        # TLS SNI and Host headers require ASCII; normalize IDN origins once.
        hostname = url.hostname.encode("idna").decode("ascii").lower()
        return "https://" + ("[" + hostname + "]" if ":" in hostname else hostname)
    except (ValueError, UnicodeError) as error:
        raise PolicyError("Canvas origin must be a valid HTTPS origin.") from error


def operation_path(operation: str, path: dict[str, str] | None) -> tuple[Operation, str]:
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise PolicyError("Unknown operation; use discover to find reviewed reads.")
    op = OPERATIONS[operation]
    if path is not None and not isinstance(path, dict):
        raise PolicyError("Path arguments must be an object.")
    values = path or {}
    if set(values) != set(op.required_path):
        raise PolicyError("Path arguments must exactly match the operation's required_path.")
    for key, value in values.items():
        pattern = r"[\w-]{1,200}" if key == "page_url" else r"[0-9]{1,20}"
        if key == "user_id":
            pattern = r"(?:self|[0-9]{1,20})"
        elif key == "event_id":
            pattern = r"(?:assignment_)?[0-9]{1,20}"
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise PolicyError("Path arguments must be simple identifiers or page slugs.")
    return op, op.path.format(**{key: quote(value, safe="") for key, value in values.items()})


def validate_query(op: Operation, query: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    allowed = set(op.query_keys) | {"page", "per_page", "bookmark", "cursor"}
    if query is not None and not isinstance(query, dict):
        raise PolicyError("Query must be an object.")
    for key, value in (query or {}).items():
        if not isinstance(key, str) or key not in allowed:
            raise PolicyError("Query parameter is not allowed for this operation.")
        values = value if isinstance(value, list) else [value]
        if not values or len(values) > 100 or (len(values) > 1 and not key.endswith("[]")):
            raise PolicyError("Invalid query array or duplicated scalar parameter.")
        converted = []
        for item in values:
            if type(item) not in (str, int, bool):
                raise PolicyError("Query values must be strings, integers or booleans.")
            text = str(item).lower() if isinstance(item, bool) else str(item)
            if len(text) > 2000 or any(ord(char) < 32 for char in text):
                raise PolicyError("Query value exceeds the allowed bounds.")
            # Reject broadly, including comma-separated and nested association syntax.
            if key.startswith("include") and "read_status" in text.lower():
                raise PolicyError(
                    "read_status is forbidden because Canvas marks submissions as read."
                )
            converted.append(text)
        if key == "auto_mark_as_read" and converted != ["false"]:
            raise PolicyError("Automatic marking as read is forbidden.")
        if key == "per_page" and (not converted[0].isdigit() or not 1 <= int(converted[0]) <= 100):
            raise PolicyError("per_page must be between 1 and 100.")
        if (
            key == "context_codes[]"
            and op.id in ("calendar", "calendar_events", "user_calendar")
            and len(values) > 10
        ):
            raise PolicyError(
                "Canvas accepts at most ten calendar contexts; make separate requests."
            )
        if (
            key == "type"
            and op.id in ("calendar", "calendar_events", "user_calendar")
            and converted[0] not in ("event", "assignment")
        ):
            raise PolicyError("Calendar type must be event or assignment.")
        result[key] = converted if isinstance(value, list) else converted[0]
    if op.id == "conversation":
        result["auto_mark_as_read"] = "false"
    return result


def build_url(origin: str, op: Operation, path: str, query: dict[str, Any] | None) -> str:
    safe = validate_query(op, query)
    encoded = urlencode(safe, doseq=True)
    return origin + path + ("?" + encoded if encoded else "")


def validate_continuation(value: str, origin: str, op: Operation, path: str) -> str:
    try:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or url.netloc.lower() != urlsplit(origin).netloc
            or url.path != path
            or url.fragment
            or url.username
            or url.password
            or "\\" in value
            or any(ord(char) < 33 for char in value)
        ):
            raise PolicyError("Unsafe pagination link was rejected.")
        query: dict[str, Any] = {}
        for key, item in parse_qsl(url.query, keep_blank_values=True, strict_parsing=True):
            if key.endswith("[]"):
                query.setdefault(key, []).append(item)
            elif key in query:
                raise PolicyError("Duplicate pagination parameter was rejected.")
            else:
                query[key] = item
        return build_url(origin, op, path, query)
    except (ValueError, UnicodeError) as error:
        raise PolicyError("Unsafe pagination link was rejected.") from error
