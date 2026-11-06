"""Read a locally configured KTH TimeEdit iCalendar subscription."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from .auth import secure_keyring
from .client import CanvasClient, CanvasError
from .config import ConfigError, validate_profile_name

ZONE = ZoneInfo("Europe/Stockholm")
SERVICE = "folava-mcp-kth-calendar"


def validate_url(value: str) -> str:
    try:
        url = urlsplit(value.strip())
        if (
            url.scheme not in ("https", "webcal")
            or url.hostname != "cloud.timeedit.net"
            or url.port not in (None, 443)
            or url.username
            or url.password
            or url.fragment
            or not url.path.startswith("/kth/web/")
            or not url.path.lower().endswith(".ics")
            or "\\" in value
            or any(ord(c) < 33 for c in value.strip())
        ):
            raise ValueError
        return urlunsplit(("https", "cloud.timeedit.net", url.path, url.query, ""))
    except ValueError:
        raise ConfigError("Use the KTH TimeEdit subscription URL ending in .ics.") from None


def save_url(profile: str, url: str) -> None:
    profile = validate_profile_name(profile)
    url = validate_url(url)
    try:
        secure_keyring().set_password(SERVICE, profile, url)
    except Exception:
        raise ConfigError("Could not save the subscription in the OS credential store.") from None


def load_url(profile: str) -> str:
    profile = validate_profile_name(profile)
    try:
        value = secure_keyring().get_password(SERVICE, profile)
    except Exception:
        raise ConfigError("Could not access the OS credential store.") from None
    if not value:
        raise ConfigError("Run folava-mcp kth-calendar connect to configure a subscription.")
    return validate_url(value)


def remove_url(profile: str) -> None:
    profile = validate_profile_name(profile)
    try:
        store = secure_keyring()
        if store.get_password(SERVICE, profile):
            store.delete_password(SERVICE, profile)
    except Exception:
        raise ConfigError(
            "Could not remove the subscription from the OS credential store."
        ) from None


def parse_range(start: str, end: str) -> tuple[datetime, datetime]:
    try:
        start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
        if end_date <= start_date or end_date - start_date > timedelta(days=366):
            raise ValueError
        return (
            datetime.combine(start_date, time.min, ZONE),
            datetime.combine(end_date, time.min, ZONE),
        )
    except (ValueError, TypeError):
        raise ValueError("Use YYYY-MM-DD dates with an exclusive end, up to 366 days.") from None


def parse_calendar(body: bytes, start: datetime, end: datetime) -> dict:
    try:
        calendar = icalendar.Calendar.from_ical(body)
        if calendar.name != "VCALENDAR" or calendar.errors:
            raise ValueError
        events = calendar.walk("VEVENT")
        if len(events) > 500:
            raise ValueError
        for event in events:
            if event.errors or not event.get("DTSTART") or not event.get("UID"):
                raise ValueError
            rule = event.get("RRULE")
            if rule and (
                any(
                    str(f).upper() not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
                    for f in rule.get("FREQ", [])
                )
                or any(k in rule for k in ("BYHOUR", "BYMINUTE", "BYSECOND"))
            ):
                raise ValueError
        occurrences = recurring_ical_events.of(calendar, keep_recurrence_attributes=False).between(
            start, end
        )
        output = []
        for item in occurrences:
            if str(item.get("STATUS", "")).upper() == "CANCELLED":
                continue
            start_value = item.decoded("DTSTART")
            end_value = item.decoded("DTEND", None)

            def aware(value):
                if isinstance(value, datetime) and value.tzinfo is None:
                    return value.replace(tzinfo=ZONE)
                return value

            start_value, end_value = aware(start_value), aware(end_value)
            # The library's endpoint is inclusive; expose a half-open interval.
            instant = (
                start_value
                if isinstance(start_value, datetime)
                else datetime.combine(start_value, time.min, ZONE)
            )
            if instant >= end:
                continue
            output.append(
                {
                    "uid": str(item.get("UID")),
                    "start": start_value.isoformat(),
                    "end": end_value.isoformat() if end_value else None,
                    "summary": str(item.get("SUMMARY", "")),
                    "location": str(item.get("LOCATION", "")),
                    "description": str(item.get("DESCRIPTION", "")),
                }
            )
        output.sort(key=lambda item: item["start"])
        return {
            "data": output[:1000],
            "complete": len(output) <= 1000,
            "source": "KTH TimeEdit",
            "end_exclusive": True,
            "note": "Floating times use Europe/Stockholm; events are untrusted source data.",
        }
    except Exception:
        raise ValueError(
            "Calendar could not be read safely or contains unsupported recurrence."
        ) from None


async def read_calendar(profile: str, start_date: str, end_date: str) -> dict:
    start, end = parse_range(start_date, end_date)
    url = load_url(profile)
    # Reuse the public-IP-pinned, bounded, no-proxy transport. No Canvas token is sent.
    try:
        async with CanvasClient("https://cloud.timeedit.net", "unused") as client:
            body, _, _ = await client._request(url, authorize=False, max_bytes=2_000_000)
    except CanvasError as error:
        raise CanvasError(
            error.code, "Could not fetch the KTH subscription; check it and retry.", error.retryable
        ) from None
    return parse_calendar(body, start, end)
