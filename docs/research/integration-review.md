# Independent integration review

Reviewed the in-progress source tree on 2026-10-28. There was no finalized commit
SHA at review start; concurrent edits were visible. No repository files changed
by this reviewer. Scope: server.py, events.py, demo.py and auth/CLI integration.

## Verdict

Coherent architecture and useful workflow surface, but not ready for a release
claim until the protocol and bounded-output issues below are resolved. Read-only
resource policy is separate from OAuth lifecycle as intended. Event transactions
preserve replayable metadata without persisting Canvas content.

## BLOCKER: real protocol test uses v1-style attributes; structured output absent

- `tests/test_server.py:38` uses `initialized.serverInfo`. Installed official MCP
  2.3.0 instead exposes `server_info`; similarly `structured_content`, `is_error`
  and `read_only_hint` are snake_case Python model fields.
- Independent escalated run of `pytest tests/test_server.py -vv -s` gave **1 failed,
  2 passed**. The real stdio test failed at `serverInfo`.
- Independently exercised official ClientSession over a real process: initialize,
  tools/list and canvas_courses all worked. However the course call returned only
  TextContent and `structured_content=None`, since SDK2 tool decorators do not
  automatically structure a plain `dict` return annotation in this configuration.
  Explicit `structured_output=True` (or a supported typed schema) is needed if the
  advertised/tested structured result contract is retained.
- Fix field access, establish structured output deliberately, rerun entire real
  protocol test. Add a finite read timeout to prevent a sandbox startup failure
  from hanging the test indefinitely.

## SHOULD-FIX: aggregate output bound is not enforced

- `src/folava_mcp/server.py:35-66`: `_bounded` limits individual strings and only a
  root-level `data` list. Single-object reads and nested agenda sources bypass its
  advertised aggregate budget.
- Deterministic reproduction: a root data dictionary with twenty 19,000-character
  fields returns **380,327 serialized characters**, `complete=True`, with no
  truncation marker. Five nested agenda sources with three 19,000-character items
  each return **285,656 characters**, also `complete=True`.
- Apply a real whole-envelope budget while retaining valid JSON and explicit
  truncation metadata. Test nested agenda sources and large single-resource dicts,
  not only one giant string.

## SHOULD-FIX: overlapping polls can roll the baseline backwards

- `src/folava_mcp/events.py:133-144`: collection fetch happens before acquiring the
  SQLite write transaction. Transactions serialize writes but not observations.
- Reproduced with asyncio barriers: baseline=old; start slow old request; commit
  a fast new request; let old request finish; poll unchanged new again. All three
  polls emit `changed`, because stale data overwrites the newest baseline.
- Serialize observation+commit for each state/query, or persist an observation
  generation and reject older in-flight observations after a newer commit.
  Include a concurrent poll regression test. This is reachable with overlapping
  scheduled poll processes or different Canvas response times.

## SHOULD-FIX: replay limit accepted by CLI exceeds backend range

- `src/folava_mcp/cli.py:365` accepts --limit 1..10000; events.read_events at line
  124 accepts only 1..1000. Values advertised as valid (e.g. 1001) fail with a
  generic CLI error. Align the ranges and include a CLI/backend boundary check.

## Finding already fixed during review

The initial config implementation deadlocked when profile name `profiles` nested
its profile lock with the global profile metadata lock. Reported immediately;
current config.py uses distinct `.metadata.lock` and `.profile-<name>.lock` files.
A regression test for the formerly valid colliding name is still worthwhile.

## Validation and limits

- Manual official-SDK process initialize/list/course call succeeded outside the
  sandbox, including clean stdout framing.
- Existing real protocol test failed as described above. Inside sandbox it hung
  with stream-fd permission errors; that is distinct from the deterministic SDK
  field failure observed outside the sandbox.
- Existing events tests verify baseline/replay, private hashes, incomplete polls,
  scope separation and final symlink refusal; these are useful but omit overlap.
- No live Canvas account, institution OAuth, Windows/macOS runtime, Codex UI or
  T3 UI integration was exercised. No inference of external evidence from mocks.

RFR readiness: **78/100**. Merge/release readiness: **65/100** at this review point.
Next action: fix the four concrete findings, run focused regression and protocol
checks, then record live validation limits in release documentation.
