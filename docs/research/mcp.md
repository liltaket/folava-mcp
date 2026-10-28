# MCP architecture research — 2026-10-28

## Recommendation

Build a single Python package with the official MCP Python SDK, an asynchronous Canvas client, a CLI, and **stdio as the default transport**. Use `src/<package>/`, `tests/`, `docs/`, a locked development environment, typed results, and MIT or Apache-2.0 licensing. Keep the API client and policy independent of MCP so the CLI, poller, and server share exactly the same request constraints.

Python 3.14.4 and pip are available on this execution machine. `uv`, `node`, and `npm` are not on PATH. This is environment evidence, not a reason to avoid Node for users. Python with `uv tool install`/`uvx --from package==VERSION command` is a good cross-platform installation story because uv isolates the application environment and supports selecting Python versions. Prefer a version-pinned installed tool for regular use; document uvx for trial use. A checkout install works before publishing a package. Do not advertise a nonexistent PyPI release.

Source: https://docs.astral.sh/uv/guides/tools/

## Current SDK, not remembered examples

Official current documentation identifies Python SDK **v2** as the stable line, Python 3.11+; the release page lists **v2.3.0**. Use `from mcp.server import MCPServer`, `@mcp.tool()`, `@mcp.resource(...)`, and `mcp.run()` for stdio. The v1 `FastMCP` import is not the current API. v2 serves legacy clients as well as the 2026-07-28 protocol; do not write a JSON-RPC implementation. Pin and actually install the chosen available version before implementing against it. Local `pip index versions mcp` could not resolve the network due to sandbox DNS, so release metadata here is browser evidence, not an installed-package verification.

Sources:
- https://py.sdk.modelcontextprotocol.io/
- https://github.com/modelcontextprotocol/python-sdk/releases
- https://py.sdk.modelcontextprotocol.io/migration/

TypeScript is also viable. Its stable v2 line is now split across `@modelcontextprotocol/server`, `@modelcontextprotocol/client`, and transport packages; the official release page lists **2.4.0**. Avoid uncritically combining current docs with old `@modelcontextprotocol/sdk` v1 samples. The latter is the maintenance line.

Sources:
- https://ts.sdk.modelcontextprotocol.io/v2/
- https://github.com/modelcontextprotocol/typescript-sdk/releases

## Transports and credentials

Stdio needs no service port or MCP login service: the host launches a local process, and Canvas credentials are provided independently through the process environment or a local credential store. All diagnostic output must go to stderr. A local CLI can implement masked token entry, profile validation, secure storage, `doctor`, `logout`, and client configuration generation. Do not expose an MCP tool that accepts the user's Canvas token: it would put credentials into model context and conversation history.

Streamable HTTP is the remote transport; old SSE is not a sensible new target. One private hosted instance would reduce repeating Canvas setup across machines, but introduces server authentication, deployment, and credential custody. Treat this as a deliberate supported mode only when it has HTTPS at the edge, correct authorization, restricted origins/hosts, request limits, and clean profile isolation. A shared unauthenticated network endpoint with a server-wide Canvas token would expose the entire account.

Sources:
- https://py.sdk.modelcontextprotocol.io/run/
- https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization

**MCP authentication and Canvas authentication are separate boundaries.** Never accept a Canvas bearer token as if it were a token issued for the MCP server, then transparently pass it through. A public multi-user service needs MCP-issued/audience-validated credentials plus separately stored per-user Canvas authorization, explicit consent, revocation, and expiry handling. An operator-provisioned single-user server credential can be suitable for private HTTP deployment, but is not a complete generic OAuth login product.

Source: https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices

## Agent-facing interface

Use a small set of task-shaped tools: courses; course outline/modules; assignment and submission details; upcoming calendar/planner entries; announcements/discussions; files and file text; and broad endpoint discovery/read. Return stable Canvas IDs, source URLs, pagination continuation, retrieval time, and explicit truncation/partial-result warnings. Keep full content accessible after a concise default result. No eager crawl of every course on server startup.

Use JSON-schema-validated input with descriptive parameter names and constrained identifiers. Annotate tools as read-only, but enforce policy in the HTTP client: annotations are hints, not authorization. Use structured output so agents do not need to parse prose. Resources can publish reference material and canonical document URIs, but core actions should also be tools because resource UI support varies by host.

Sources:
- https://py.sdk.modelcontextprotocol.io/servers/tools/
- https://modelcontextprotocol.io/specification/2026-07-28/server/resources

## Broad coverage without a dangerous escape hatch

A generic `GET any supplied URL` tool is insufficient. Implement an audited registry of permitted **relative endpoint templates**, with allowed query parameters and required safe overrides. A discovery tool can search this registry and return the endpoint ID, path parameters, and query schema. The read tool accepts an endpoint ID and structured values, never an arbitrary origin or HTTP method.

The transport should have no arbitrary-method API available to handlers. Reject traversal, encoded traversal, protocol-relative URLs, userinfo, fragments, backslashes and alternate hosts; constrain every pagination URL to the configured HTTPS origin and approved route. Reject `_method` and other method override tricks. Never send Authorization to third-party file hosts; file redirects need their own validation and size/time bounds. Block POST-backed GraphQL rather than pretending POST is read-only.

GET alone does not guarantee unchanged user state. Canvas conversation retrieval, for instance, needs `auto_mark_as_read=false`; the policy must force it, including for generic discovery reads and pagination. Do not silently interpret inaccessible content as an empty collection. “Everything” must mean audited read operations within the authenticated user's permissions; inaccessible roles, third-party LTI content, and endpoints with stateful GET behavior cannot be promised.

Canvas source: https://developerdocs.instructure.com/services/canvas/resources/conversations

## Events and wakeups

MCP change notifications are useful invalidation signals to connected, subscribing clients. They do **not** specify starting an agent turn or waking a closed desktop client. Current Python SDK subscriptions are an open client request stream, not a durable queue or replay log. Legacy and 2026 clients use different notification paths; supporting only one path must not be presented as universal event support.

The dependable personal-use solution is a separately run poller with bounded GET pagination, durable state, stable event IDs, initial baseline behavior, retry/backoff, and JSON Lines output. External automation can consume those events and explicitly start an agent using its own supported mechanism. Keep executable shell hooks off by default. If HTTP webhook sinks are implemented, make them explicit opt-in; Canvas-derived content is untrusted data, not instructions. Do not promise Canvas Live Events to ordinary students without confirming institutional access separately.

Source: https://py.sdk.modelcontextprotocol.io/handlers/subscriptions/

## Acceptance evidence worth requiring

- Protocol smoke test through the actual installed SDK client over stdio, including tool discovery, one mock-backed tool call, schema rejection, and clean stdout framing.
- Transport tests prove GET-only use and reject cross-origin redirects/pagination, encoded path bypasses, method overrides, and dangerous query arguments.
- End-to-end mock API verifies list pagination, rate limiting, denial vs empty results, malformed payloads, file size/time limits, and content truncation markers.
- Auth setup and logout tests use temporary stores; secret values never appear in stdout, errors, generated config, or snapshots.
- Poller tests cover first baseline, changed/removed entities, restart persistence, partial fetch failure, and duplicate prevention.
- Build and install wheel in an isolated environment. Examples must use the actual package/CLI entrypoint and distinguish source installation from a published release.
- Live-account verification requires real credentials; state plainly when this has not occurred. Do not upgrade mock or protocol evidence into live institution compatibility.
