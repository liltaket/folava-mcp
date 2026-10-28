# Architecture

One installable Python package. No database server, hosted login, browser wrapper,
LLM SDK or background service is required.

```text
MCP tools ─┐
CLI reads ─┼─ CanvasClient ─ policy + catalog ─ public HTTPS Canvas REST
Poller ────┘        └─ file metadata + public_url API ─ audited S3 REST storage

Human auth CLI ─ OAuth credential lifecycle ─ OS keyring
                       └─ secret-free profile metadata
Poller ─ private SQLite hashes + replayable observations
```

`catalog.py` defines reviewed operation templates and their allowed query keys.
`policy.py` builds single-segment paths and validates both initial and pagination
queries. `client.py` offers only resource GETs. Stateful/ambiguous action endpoints
and POST GraphQL are excluded; there is no unsafe escape hatch. Broad coverage
means reviewed API resources within current permissions, not every Canvas feature.
Known stateful detail routes and unresolved direct page reads are excluded; page
collections with optional bodies remain available. See
[excluded reads](tools.md#excluded-reads).
Canvas access logging and derived-cache refreshes can still occur during GET.

Requests use HTTPS port 443, no environment proxies, public-only DNS resolution
and a pinned TCP destination with the original Host and TLS SNI. Mixed public and
private DNS answers fail closed. Keepalive is disabled to prevent TLS connection
reuse across original hostnames sharing a pinned IP. API redirects are refused;
attachment content accepts audited AWS S3 REST endpoints only, with every hop
validated before networking and no Canvas authorization or cookies. Metadata UI
URLs are never fetched. Canvas/local file routes, InstFS, CDN and custom storage
backends are refused. A trusted injected HTTP transport exists only for
deterministic unit tests. Private-network Canvas installations require a separately designed
narrow network policy; there is no global disable-security option.

Resource reads allow 1–20 pages, 20,000 items, up to 10 MB decoded JSON per response
and 20 MB aggregate, with a 90-second operation deadline. Compressed responses
are rejected before decoding; upstream servers must honor identity encoding. Requests serialize per
client. Retries are bounded and respect a capped numeric Retry-After. Per-process
and cross-machine calls still share Canvas's token-level quota. Tool output has an
additional aggregate JSON budget; binary file payloads have an explicit byte cap.

`auth.py` is a separate credential boundary. Only it exchanges/refreshes OAuth
credentials or explicitly revokes them; these methods are absent from agent tools.
Profile locks protect refresh and metadata changes between local processes. The
MCP server loads current credentials per tool operation so a persistent server
can survive access-token expiry. No server port is opened in stdio mode; the OAuth
CLI opens a temporary loopback callback while a person signs in.

`events.py` stores query-bound hashes and minimal observations in SQLite. It rejects
overlaps before fetch, commits baseline and events together, and supports replay.
It does not crawl all courses automatically or infer deletions from failed reads.

`demo.py` is an entirely synthetic fixture, clearly marked in its responses. It
requires neither credentials nor networking. The demo is a protocol/product tour,
not a claim of live Canvas behavior.

See the [research](research/canvas.md), [MCP rationale](research/mcp.md),
[build map](build-map.md) and [release gates](release-readiness.md).

Agenda reads share a client and credential load across sources, preserve partial
failures and stop after 45 seconds overall. JSON reads reject nesting over 100
levels and excessive structural complexity before parsing; result clipping has a
separate depth budget. Resource transport neither persists cookies nor emits
HTTPX request logs containing signed attachment capabilities.
