import pytest
from typer.testing import CliRunner

from folava_mcp import kth_calendar as kth
from folava_mcp.cli import app
from folava_mcp.config import ConfigError
from folava_mcp.server import create_server

URL = "webcal://cloud.timeedit.net/kth/web/student/secret.ics"
ICS = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:lecture\r
DTSTART;TZID=Europe/Stockholm:20261019T100000\r
DTEND;TZID=Europe/Stockholm:20261019T110000\r
RRULE:FREQ=WEEKLY;COUNT=3;BYDAY=MO\r
EXDATE;TZID=Europe/Stockholm:20261026T100000\r
SUMMARY:Lecture\r
LOCATION:Room 1\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:all-day\r
DTSTART;VALUE=DATE:20261027\r
DTEND;VALUE=DATE:20261028\r
SUMMARY:All day\r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_url_validation():
    assert kth.validate_url(URL) == URL.replace("webcal:", "https:")
    for value in (
        "https://example.com/kth/web/x.ics",
        "http://cloud.timeedit.net/kth/web/x.ics",
        "https://cloud.timeedit.net/other/x.ics",
        "https://evil@cloud.timeedit.net/kth/web/x.ics",
    ):
        with pytest.raises(ConfigError):
            kth.validate_url(value)


def test_recurrence_exception_timezone_all_day_and_exclusive_end():
    start, end = kth.parse_range("2026-10-01", "2026-11-02")
    result = kth.parse_calendar(ICS, start, end)
    assert result["complete"]
    assert [(e["uid"], e["start"]) for e in result["data"]] == [
        ("lecture", "2026-10-19T10:00:00+02:00"),
        ("all-day", "2026-10-27"),
    ]


def test_invalid_input_fails_closed():
    with pytest.raises(ValueError):
        kth.parse_range("2026-01-01", "2028-01-01")
    start, end = kth.parse_range("2026-10-01", "2026-11-01")
    for body in (b"<html>login</html>", ICS.replace(b"WEEKLY", b"SECONDLY")):
        with pytest.raises(ValueError):
            kth.parse_calendar(body, start, end)


def test_connect_hides_secret_and_disconnect(monkeypatch):
    class Store:
        data = {}

        def set_password(self, service, name, value):
            self.data[(service, name)] = value

        def get_password(self, service, name):
            return self.data.get((service, name))

        def delete_password(self, service, name):
            del self.data[(service, name)]

    store = Store()
    monkeypatch.setattr(kth, "secure_keyring", lambda: store)
    result = CliRunner().invoke(app, ["kth-calendar", "connect"], input=URL + "\n")
    assert result.exit_code == 0, result.output
    assert URL not in result.output
    assert kth.load_url("default").endswith("/secret.ics")
    assert CliRunner().invoke(app, ["kth-calendar", "disconnect"]).exit_code == 0
    with pytest.raises(ConfigError):
        kth.load_url("default")


async def test_mcp_reads_and_reports_failures_without_link(monkeypatch):
    async def fake(profile, start, end):
        assert profile == "default"
        return kth.parse_calendar(ICS, *kth.parse_range(start, end))

    monkeypatch.setattr(kth, "read_calendar", fake)
    result = await create_server().call_tool(
        "kth_schedule", {"start_date": "2026-10-01", "end_date": "2026-11-02"}
    )
    assert result.structured_content["complete"]
    assert URL not in str(result.structured_content)


async def test_read_fetches_only_the_configured_feed_without_auth(monkeypatch):
    import httpx

    from folava_mcp.client import CanvasClient

    requests = []

    async def handle(request):
        requests.append(request)
        return httpx.Response(200, content=ICS)

    monkeypatch.setattr(kth, "load_url", lambda profile: kth.validate_url(URL))
    monkeypatch.setattr(
        kth,
        "CanvasClient",
        lambda origin, token: CanvasClient(origin, token, transport=httpx.MockTransport(handle)),
    )
    result = await kth.read_calendar("default", "2026-10-01", "2026-11-02")
    assert result["complete"] and len(result["data"]) == 2
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert str(requests[0].url) == kth.validate_url(URL)
    assert "authorization" not in requests[0].headers
    assert "secret.ics" not in str(result)
