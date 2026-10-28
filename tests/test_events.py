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


def test_meaningful_url_query_and_fragment_changes_emit_events(tmp_path):
    path = tmp_path / "events.db"

    def record(url):
        return record_snapshot(
            path, scope="s", operation="pages", complete=True, items=[{"id": 1, "url": url}]
        )

    assert record("https://example.edu/material?lesson=1#part-one") == []
    assert [e["kind"] for e in record("https://example.edu/material?lesson=2#part-one")] == [
        "changed"
    ]
    assert [e["kind"] for e in record("https://example.edu/material?lesson=2#part-two")] == [
        "changed"
    ]


def test_storage_failure_rolls_back_events_snapshot_and_revision(tmp_path):
    path = tmp_path / "events.db"
    record_snapshot(path, scope="s", operation="courses", items=[{"id": 1}], complete=True)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TRIGGER simulated_failure BEFORE INSERT ON events "
            "BEGIN SELECT RAISE(ABORT, 'simulated disk error'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        record_snapshot(path, scope="s", operation="courses", items=[{"id": 2}], complete=True)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT revision FROM scopes WHERE id='s'").fetchone() == (1,)
        assert db.execute("SELECT entity FROM snapshots WHERE scope='s'").fetchall() == [("1",)]
        db.execute("DROP TRIGGER simulated_failure")
    assert read_events(path) == []
    events = record_snapshot(path, scope="s", operation="courses", items=[{"id": 2}], complete=True)
    assert {event["kind"] for event in events} == {"created", "removed"}
    assert read_events(path) == events


def test_concurrent_same_snapshot_commits_one_change(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "events.db"
    record_snapshot(path, scope="s", operation="courses", items=[{"id": 1}], complete=True)
    barrier = threading.Barrier(4)

    def update():
        barrier.wait(timeout=2)
        return record_snapshot(
            path,
            scope="s",
            operation="courses",
            items=[{"id": 1, "name": "changed"}],
            complete=True,
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        batches = list(executor.map(lambda _: update(), range(4)))
    events = [event for batch in batches for event in batch]
    assert len(events) == 1
    assert events[0]["kind"] == "changed"
    assert read_events(path) == events


async def test_poll_failure_restart_and_exact_query_identity(tmp_path):
    from folava_mcp.events import poll_once

    class Client:
        origin = "https://canvas.example"
        user_id = 42
        items = [{"id": 1, "name": "original"}]
        complete = True
        error = None

        async def read(self, operation, *args, **kwargs):
            if operation == "profile":
                return {"data": {"id": self.user_id}}
            if self.error:
                raise self.error
            return {"data": self.items, "complete": self.complete}

    path = tmp_path / "events.db"
    client = Client()
    assert await poll_once(client, path, "assignments", {"course_id": "1"}) == []
    client.items = []
    client.complete = False
    with pytest.raises(IncompletePoll):
        await poll_once(client, path, "assignments", {"course_id": "1"})
    client.complete = True
    client.error = RuntimeError("simulated transient network failure")
    with pytest.raises(RuntimeError):
        await poll_once(client, path, "assignments", {"course_id": "1"})
    assert read_events(path) == []
    restarted = Client()
    restarted.items = [{"id": 1, "name": "changed"}]
    events = await poll_once(restarted, path, "assignments", {"course_id": "1"})
    assert [event["kind"] for event in events] == ["changed"]
    for account, course, query in [
        (99, "1", None),
        (42, "2", None),
        (42, "1", {"search_term": "new query"}),
    ]:
        restarted.user_id = account
        assert await poll_once(restarted, path, "assignments", {"course_id": course}, query) == []
    assert read_events(path) == events


def test_signed_file_expiry_changes_ignore_only_volatile_arguments(tmp_path):
    path = tmp_path / "events.db"
    for signature in ("first", "second"):
        assert (
            record_snapshot(
                path,
                scope="s",
                operation="files",
                complete=True,
                items=[
                    {
                        "id": 1,
                        "url": "https://cdn.example/file?lesson=1&"
                        f"X-Amz-Signature={signature}&X-Amz-Expires=100&verifier={signature}",
                    }
                ],
            )
            == []
        )
    changed = record_snapshot(
        path,
        scope="s",
        operation="files",
        complete=True,
        items=[{"id": 1, "url": "https://cdn.example/file?lesson=2&X-Amz-Signature=third"}],
    )
    assert [event["kind"] for event in changed] == ["changed"]
