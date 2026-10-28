"""Transactional, replayable observations. Canvas content is never an instruction."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class IncompletePoll(ValueError):
    """An incomplete collection cannot become a new baseline."""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _stable(value: Any) -> Any:
    # Expiring file URLs should not turn an unchanged attachment into an event.
    from urllib.parse import urlsplit, urlunsplit

    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            if key in (
                "url",
                "download_url",
                "preview_url",
                "thumbnail_url",
                "avatar_url",
            ) and isinstance(item, str):
                parsed = urlsplit(item)
                item = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
            output[key] = _stable(item)
        return output
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@contextmanager
def _database(path: Path):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Event database must not be a symbolic link.")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    os.close(fd)
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise ValueError("Event database must be private (chmod 600).")
    db = sqlite3.connect(path, timeout=10)
    try:
        # DELETE journaling inherits database permissions; no persistent WAL files.
        db.execute("PRAGMA journal_mode=DELETE")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS scopes (
                id TEXT PRIMARY KEY, revision INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                scope TEXT NOT NULL, entity TEXT NOT NULL, digest TEXT NOT NULL,
                PRIMARY KEY (scope, entity)
            );
            CREATE TABLE IF NOT EXISTS events (
                cursor INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE, scope TEXT NOT NULL,
                operation TEXT NOT NULL, entity TEXT NOT NULL,
                kind TEXT NOT NULL, observed_at TEXT NOT NULL
            );
        """)
        yield db
    finally:
        db.close()


def record_snapshot(
    state_path: Path,
    *,
    scope: str,
    operation: str,
    items: list[dict],
    complete: bool,
) -> list[dict]:
    """Commit hashes and events together; baseline emits nothing; replay via read_events.

    Removals mean no longer visible in this successful query, never a proof that
    somebody deleted the source object. Scope is bound to account + exact query.
    """
    if not complete:
        raise IncompletePoll("Poll was incomplete; saved baseline has not changed.")
    if len(items) > 100_000:
        raise IncompletePoll("Poll exceeds the snapshot limit; baseline has not changed.")
    current: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("id") is None:
            raise IncompletePoll("Poll needs a complete collection with stable object IDs.")
        entity = str(item["id"])
        if entity in current or len(entity) > 512:
            raise IncompletePoll("Duplicate or invalid object ID; baseline has not changed.")
        current[entity] = _hash(_stable(item))
    now = datetime.now(UTC).isoformat()
    result = []
    with _database(state_path) as db:
        # The read and update must share one write lock across concurrent pollers.
        db.execute("BEGIN IMMEDIATE")
        try:
            prior = db.execute("SELECT revision FROM scopes WHERE id=?", (scope,)).fetchone()
            revision = (prior[0] if prior else 0) + 1
            old = dict(db.execute("SELECT entity,digest FROM snapshots WHERE scope=?", (scope,)))
            if prior:
                changes = [(key, "created") for key in current.keys() - old.keys()]
                changes += [
                    (key, "changed")
                    for key in current.keys() & old.keys()
                    if current[key] != old[key]
                ]
                changes += [(key, "removed") for key in old.keys() - current.keys()]
                for entity, kind in sorted(changes):
                    event_id = _hash([scope, revision, entity, kind, current.get(entity)])
                    cursor = db.execute(
                        "INSERT INTO events(event_id,scope,operation,entity,kind,observed_at) "
                        "VALUES(?,?,?,?,?,?)",
                        (event_id, scope, operation, entity, kind, now),
                    ).lastrowid
                    result.append(
                        dict(
                            cursor=cursor,
                            event_id=event_id,
                            scope=scope,
                            operation=operation,
                            entity_id=entity,
                            kind=kind,
                            observed_at=now,
                        )
                    )
            db.execute("DELETE FROM snapshots WHERE scope=?", (scope,))
            db.executemany(
                "INSERT INTO snapshots VALUES(?,?,?)",
                [(scope, key, value) for key, value in current.items()],
            )
            db.execute("INSERT OR REPLACE INTO scopes VALUES(?,?)", (scope, revision))
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return result


def read_events(state_path: Path, after: int = 0, limit: int = 100) -> list[dict]:
    """Replay persisted events after a caller-owned cursor (at-least-once delivery)."""
    if after < 0 or not 1 <= limit <= 1000:
        raise ValueError("Cursor must be non-negative; limit must be 1–1000.")
    with _database(state_path) as db:
        db.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in db.execute(
                "SELECT cursor,event_id,scope,operation,entity AS entity_id,kind,observed_at "
                "FROM events WHERE cursor>? ORDER BY cursor LIMIT ?",
                (after, limit),
            )
        ]


@contextmanager
def _poll_lock(state_path: Path):
    """Reject overlapping runs before fetching; old responses cannot roll state back."""
    lock = Path(str(state_path) + ".poll.lock")
    lock.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if lock.is_symlink():
        raise IncompletePoll("Poll lock must not be a symbolic link.")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    acquired = False
    try:
        try:
            if os.name == "nt":
                import msvcrt

                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            raise IncompletePoll(
                "Another poll is running for this state database; retry later."
            ) from None
        yield
    finally:
        if acquired:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


async def poll_once(
    client,
    state_path: Path,
    operation: str,
    path: dict | None = None,
    query: dict | None = None,
) -> list[dict]:
    with _poll_lock(state_path):
        identity = await client.read("profile")
        user_id = identity["data"].get("id")
        if user_id is None:
            raise IncompletePoll("Canvas identity did not include a stable ID.")
        response = await client.read(operation, path, query, max_pages=20)
        if not isinstance(response["data"], list):
            raise IncompletePoll("Polling requires a collection operation.")
        scope = _hash(
            ["catalog-v1", client.origin, str(user_id), operation, path or {}, query or {}]
        )
        return record_snapshot(
            state_path,
            scope=scope,
            operation=operation,
            items=response["data"],
            complete=response["complete"],
        )
