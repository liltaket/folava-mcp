import runpy
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from folava_mcp.client import CanvasError

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/check_canvas.py"))


async def test_live_transport_has_an_independent_write_and_ui_guard():
    called = []

    def handler(request):
        called.append(request)
        return httpx.Response(200, json=[])

    audit = MODULE["ReadAudit"]("https://canvas.example")
    transport = audit.wrap(httpx.MockTransport(handler))
    for request in (
        httpx.Request("POST", "https://canvas.example/api/v1/courses"),
        httpx.Request("GET", "https://canvas.example/files/1/download"),
        httpx.Request(
            "GET", "https://storage.example/file", headers={"Authorization": "Bearer fixture"}
        ),
    ):
        with pytest.raises(CanvasError) as error:
            await transport.handle_async_request(request)
        assert error.value.code == "audit"
    assert called == [] and audit.methods == {}


async def test_live_transport_budget_caps_real_network_attempts():
    called = []

    def handler(request):
        called.append(True)
        return httpx.Response(200, json=[])

    audit = MODULE["ReadAudit"]("https://canvas.example", max_requests=1)
    transport = audit.wrap(httpx.MockTransport(handler))
    request = httpx.Request(
        "GET", "https://93.184.216.34/api/v1/courses", extensions={"sni_hostname": "canvas.example"}
    )
    await transport.handle_async_request(request)
    with pytest.raises(CanvasError) as error:
        await transport.handle_async_request(request)
    assert error.value.code == "budget" and len(called) == 1
    assert audit.methods == {"GET": 1} and audit.statuses == {"200": 1}


def test_live_report_never_echoes_identity_content_or_error_bodies():
    summarize = MODULE["result_summary"]
    private = {"id": 123, "name": "Private Student", "body": "private homework"}
    result = summarize("case", {"data": [private], "complete": False})
    assert result == {
        "scenario": "case",
        "status": "ok",
        "complete": False,
        "shape": "list",
        "items": 1,
    }
    error = summarize("case", {"error": {"code": "forbidden", "message": "private details"}})
    assert error == {"scenario": "case", "status": "unavailable", "error_code": "forbidden"}


def test_progress_comparison_distinguishes_completion_metadata_and_membership():
    compare = MODULE["compare_progress"]

    def item(identifier=7, *, completed=False, minimum=1):
        return {
            "id": identifier,
            "title": "private title",
            "completion_requirement": {
                "type": "must_view",
                "completed": completed,
                "min_score": minimum,
            },
        }

    before = [item()]
    assert compare(before, [item()])["classification"] == "same"
    completion = compare(before, [item(completed=True)])
    assert completion == {
        "classification": "completed_changed",
        "membership_changes": 0,
        "completed_changes": 1,
        "requirement_metadata_changes": 0,
    }
    assert compare(before, [item(minimum=2)])["classification"] == "requirement_metadata_changed"
    assert compare(before, [item(8)])["classification"] == "membership_changed"
    assert (
        compare(before, [item(completed=True, minimum=2)])["classification"] == "multiple_changes"
    )
    # No raw identifiers, titles, requirement values or body fields leave the comparator.
    assert "private title" not in str(completion) and "must_view" not in str(completion)
    assert compare([], [])["classification"] == "same"


@pytest.mark.parametrize("after", [None, {}, [{"title": "missing id"}], [{"id": 1}, {"id": 1}]])
def test_progress_comparison_reports_missing_or_ambiguous_samples(after):
    assert MODULE["compare_progress"]([], after) == {"classification": "unavailable"}


def test_live_cli_reports_credential_file_failure_with_nonzero_exit_and_no_traceback(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts/check_canvas.py"),
            "--origin",
            "https://canvas.example",
            "--token-file",
            str(tmp_path / "missing"),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert '"error_code": "validation_failed"' in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
