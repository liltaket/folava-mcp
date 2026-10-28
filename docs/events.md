# Observe changes

The poller makes read-only REST requests and compares a complete collection with
its previous snapshot. It is useful for a scheduled study assistant, not a complete
Canvas audit log. Changes that occur and disappear between polls can be missed.

```sh
folava-mcp poll assignments \
  --path '{"course_id":"101"}' \
  --state ./course-101.sqlite
```

The first successful run establishes a baseline and prints nothing. Later runs
print new events as JSON Lines. The SQLite database atomically stores hashes and
events. It contains private metadata, even though coursework bodies are not saved.
Do not commit it. The requested folder is created if needed; the database must be
owner-only on POSIX. On Windows protect the folder with your user ACL.

Each event carries a durable cursor, event ID, query-scope hash, operation, Canvas
entity ID, observation time and kind (`created`, `changed`, `removed`). `removed`
means no longer visible in this successful query, not proven deletion at Canvas.
The scope is bound to origin, Canvas identity, operation, path, query and catalog
version. Changing filters establishes a new baseline. Only recognized volatile signature/expiry
query parameters are excluded from item hashes. Meaningful query parameters and
fragments remain part of the comparison.

Incomplete pagination, errors, missing IDs and duplicate IDs never replace the
baseline. Overlapping polls of one state database are rejected before fetching so
an old request cannot roll the baseline back. The limit is 20 pages per poll;
large collections should be divided into smaller stable queries.

## Replay and start an agent

```sh
folava-mcp events read --state ./course-101.sqlite --after 0 --limit 100
```

Schedule `poll` using your OS scheduler, then let a trusted automation consumer
read events after its last acknowledged cursor. Persist that cursor only after the
consumer has completed its work; deduplicate by event ID. Delivery is at least
once. A crash after commit but before stdout is recoverable through replay.
The feed is retained until you delete the database; no silent retention cutoff
invalidates a consumer's cursor.

The consumer can read the changed object by ID and start its chosen agent through
that host's documented interface. Keep arguments fixed and feed structured data
through stdin; never interpolate course text into a shell command. This release
does not execute shell hooks or send coursework to a webhook destination.

MCP does not guarantee waking an idle or closed agent. Canvas Live Events needs
institutional administrator configuration and is not included. Polling plus your
scheduler is the supported event mechanism. Start with a gentle cadence such as
15 minutes, watch rate-limit responses and back off when necessary.
