import sqlite3

import pytest

from folava_mcp.events import IncompletePoll, read_events, record_snapshot


def test_restart_replay_and_content_minimization(tmp_path):
    path = tmp_path / "events.db"

    def record(items, **kwargs):
        return record_snapshot(
            path,
            scope="account-query",
            operation="assignments",
            items=items,
            complete=kwargs.get("complete", True),
        )

    assert record([{"id": 1, "body": "private homework"}]) == []
    events = record([{"id": 1, "body": "changed private homework"}, {"id": 2}])
    assert {e["kind"] for e in events} == {"changed", "created"}
    assert record([{"id": 1, "body": "changed private homework"}, {"id": 2}]) == []
    assert read_events(path) == events
    assert read_events(path, after=events[0]["cursor"]) == events[1:]
    assert "private homework" not in path.read_bytes().decode(errors="ignore")
    assert record([{"id": 1, "body": "changed private homework"}])[0]["kind"] == "removed"


def test_failed_snapshot_never_advances_baseline(tmp_path):
    path = tmp_path / "events.db"
    record_snapshot(path, scope="s", operation="a", items=[{"id": 1}], complete=True)
    for items, complete in [
        ([], False),
        ([{"body": "no id"}], True),
        ([{"id": 2}, {"id": 2}], True),
    ]:
        with pytest.raises(IncompletePoll):
            record_snapshot(path, scope="s", operation="a", items=items, complete=complete)
    assert read_events(path) == []
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT entity FROM snapshots").fetchall() == [("1",)]


def test_account_query_scope_separation(tmp_path):
    path = tmp_path / "events.db"
    for scope, items in [("account-1", [{"id": 1}]), ("account-2", []), ("new-query", [])]:
        assert record_snapshot(path, scope=scope, operation="a", items=items, complete=True) == []
    assert read_events(path) == []


def test_refuse_symlink(tmp_path):
    target = tmp_path / "secret"
    target.write_text("keep")
    link = tmp_path / "events.db"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic"):
        read_events(link)
    assert target.read_text() == "keep"


async def test_overlapping_poller_cannot_commit_old_snapshot(tmp_path):
    import asyncio

    from folava_mcp.events import poll_once

    started, release = asyncio.Event(), asyncio.Event()

    class SlowClient:
        origin = "https://canvas.example"

        async def read(self, op, *args, **kwargs):
            if op == "profile":
                return {"data": {"id": 11}}
            started.set()
            await release.wait()
            return {"data": [{"id": 1}], "complete": True}

    path = tmp_path / "events.db"
    task = asyncio.create_task(poll_once(SlowClient(), path, "courses"))
    await started.wait()
    with pytest.raises(IncompletePoll, match="Another poll"):
        await poll_once(SlowClient(), path, "courses")
    release.set()
    assert await task == []


def test_volatile_file_signatures_do_not_create_changes(tmp_path):
    path = tmp_path / "events.db"
    for signature in ("old", "new"):
        assert (
            record_snapshot(
                path,
                scope="a",
                operation="files",
                complete=True,
                items=[{"id": 1, "url": f"https://files.example/f?signature={signature}"}],
            )
            == []
        )
