# Independent architecture/security review — Folava Canvas MCP

Reviewed 2026-10-28. Design review only: no implementation, installed SDK, real institution account, or live behavioral tests were validated. Read the supplied proposal and the two /tmp research reports; independently consulted primary sources below. No remote objects created.

## Verdict

The stdio-first package and discovery plus audited-operation execution are sound foundations. They are not yet launch evidence. Proceed with implementation and local mock validation, but resolve the policy approval gate before offering a supported Canvas integration. Keep HTTP and automatic file extraction out of the initial supported surface unless their separate gates are met.

## BLOCKER: current policy explicitly addresses MCP

Location: launch/distribution claims and onboarding.

The current [Canvas API Policy, section 3(i)](https://www.instructure.com/policies/canvas-api-policy) includes the restriction: “using model context protocol servers or other technologies not approved by Instructure”. The surrounding clause concerns connecting to, integrating with, or accessing its products, services, APIs or related documentation. Obtain clarification/approval applicable to this connector before claiming an authorized production integration. Institution-issued OAuth credentials do not themselves prove Instructure approval. Open-source licensing, GET-only operation, and personal deployment do not establish an exception. Applicability to an independently operated open-source Canvas deployment needs separate confirmation; do not infer it from the hosted policy.

The same policy requires transparency about GAI and handling/disclosure of private student information. Explain that selected Canvas content enters the chosen MCP host/model and its retention regime; do not promise no training or storage unless the deployment actually establishes that.

Acceptance: release checklist records the applicable approval/terms and deployment scope. This is a launch gate, not a reason to invent a technical workaround.

## BLOCKER: personal tokens are not commercial onboarding

Location: authentication documentation and setup flow.

[Canvas OAuth overview](https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth) describes manual tokens for testing one's application before implementing OAuth; asking another user to generate and enter a token violates the stated policy, and multi-user applications must use OAuth. This is broader than “commercial apps must use OAuth”: being free/open-source does not provide an exemption. Conversely the inspected policy does not state a blanket rule that every commercial API use or developer key requires a paid partnership. Do not claim that either. “Own/testing” is defensible as a narrow developer mode, not proof of unrestricted permanent personal production use or a general public bring-your-own-token onboarding route.

Acceptance: no normal user tutorial asks customers to paste personal tokens. Developer mode is explicit; secrets enter via process configuration/keychain, never MCP tool arguments. Commercial deployment requires applicable terms/approval plus OAuth, not merely an OAuth checkbox.

## BLOCKER: specify an achievable OAuth client deployment

Location: OAuth provisioning and credential custody.

[Developer keys](https://developerdocs.instructure.com/services/canvas/oauth2/file.developer_keys) are institution-scoped unless issued globally and enabled; students cannot assume they can self-register an application. A key must allow the audited endpoint scopes. API scopes constrain endpoints, not all query behavior.

[Canvas endpoint documentation](https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth_endpoints) documents authorization-code flow, a client secret at token exchange, and native out-of-band redirect handling. It does not document a PKCE/public-client, device-code, or dynamic-registration flow. Absence in these docs is not proof of universal non-support; it is enough to reject a promised turnkey public desktop OAuth flow without institution testing. Do not embed a shared developer secret in a public Python package. Choose institution/operator-managed confidential credentials or an approved hosted broker; the broker materially expands security and privacy scope.

Acceptance: institution test demonstrates consent, exact configured redirect, state replay/mismatch rejection, cancellation, code exchange, refresh, expiry and revoked-key behavior. Bind tokens to canonical Canvas origin plus account identity; atomically persist refreshed access tokens and serialize concurrent refresh. Document exactly which deployment owns the secret. OAuth lifecycle POSTs are allowed in a separate credential component; never expose them through the GET catalogue.

## BLOCKER: read-only must be an endpoint-and-parameter invariant

Location: shared policy/transport layer, used by MCP, CLI, poller and pagination.

[Conversation detail](https://developerdocs.instructure.com/services/canvas/resources/conversations) defaults auto_mark_as_read to true: force a serialized false value. [Submissions](https://developerdocs.instructure.com/services/canvas/resources/submissions) explicitly warns that including read_status marks submissions read: deny that include value for every applicable route.

Do not treat discussion forced_read_state=false as a universal “do not mark read” switch. [Discussion documentation](https://developerdocs.instructure.com/services/canvas/resources/discussion_topics) also uses this property for manually forced state and on mutating mark-read endpoints; false on such a mutation does not make it read-only. Require route-specific evidence for each GET and preserve existing forced-unread state. Exclude any ambiguous operation until verified.

Acceptance tests:

- Every entry has a fixed method, path template, parameter schema, allowed includes, scope and side-effect review. Discovery cannot add entries or weaken validation; execution independently rejects unknown IDs.
- Reject extra parameters, duplicate/query aliases, method overrides, access_token, as_user_id, arbitrary headers, arbitrary paths/URLs and unsafe encoded path segments. Validate IDs without assuming every Canvas identifier is a simple integer unless the operation explicitly requires one.
- Exercise overrides through named tools, execution, pagination and poller. A hostile next link cannot re-enable auto-read or add read_status.
- Fixture tests assert emitted requests. Separately, controlled Canvas tests compare unread conversation/submission/discussion and manually forced state before/after. Do not label mocked request tests proof of Canvas behavior.
- Read-only means no intended resource/read-state mutations; ordinary server access logs and OAuth lifecycle changes are not literally absent.

## BLOCKER if downloads ship: SSRF and capability leakage

Location: URL handling, pagination, file client and result serializer.

Recommendations: canonical HTTPS Canvas origin is trusted operator configuration, never tool input. Follow API pagination only within the same origin and audited route. Disable automatic redirects on authenticated API calls. File metadata is obtained by audited ID; arbitrary attachment URLs are not automatically fetched. If external download support ships, isolate it in a credential-free client with validated destinations and bounded redirect hops. Treat signed URLs as credentials and omit them from logs and durable event records.

Acceptance: test cross-origin and same-origin unsafe redirects; userinfo, fragments, downgrade, alternate ports, IPv4/IPv6 loopback/private/link-local destinations, mixed DNS answers and rebinding between resolution and connection. The actual connection must use a validated destination; preflight DNS alone is insufficient. Explicit trusted private Canvas deployments need a narrow configured exception, never a global SSRF disable. Disable unintended environment proxy inheritance. Stream byte limits despite false Content-Length, bound decompression/extraction, reject path traversal/symlink writes, never execute content, and clean temporary files on cancellation. Initial metadata-only files are an acceptable limitation.

## SHOULD-FIX: boundedness and truthful completeness

Location: Canvas client and response envelope.

Use explicit aggregate request/page/item/decoded-byte/time limits, small concurrency, bounded transient retries with jitter and capped Retry-After, and immediate cancellation. Never retry permission failures indefinitely. Preserve machine-readable partial/error state and continuation rather than silently presenting a complete collection. Reject continuation cycles and bind cursors to origin, identity, operation and parameters; clients must not supply arbitrary next URLs.

Acceptance: oversized/chunked/compressed responses, malformed JSON and Link, empty intermediate pages with next links, 429/503 storms, slow streams and cancellation terminate within configured budgets. Include result provenance, retrieval time and truncation. Large HTML strings cannot evade the output-byte cap. No credentials or sensitive response bodies appear in errors. Canvas content is untrusted data: sanitize renderable HTML, label provenance, and never interpret instructions inside assignments or attachments as connector commands.

## SHOULD-FIX: polling is observation, not a change log

Location: JSONL state machine and cron bridge.

Hash canonical selected fields; exclude volatile URLs/order where semantically irrelevant. Namespace state by Canvas origin/user/query/catalogue version. Baseline the first run, use locks and atomic durable checkpointing, and define delivery as at-least-once with deterministic event IDs and consumer deduplication. A crash between append and checkpoint must not silently lose changes. JSONL and state contain private metadata even if bodies are hashed; hashes are not anonymization.

Acceptance: restart/crash tests, overlapping cron invocations, malformed final JSONL line, disk full, consumer failure, reorder-only changes, and catalogue migration. No deletion inference from capped/failed collections or lost access. Even a complete absence generally means “no longer visible”, not proven deletion. Polling can miss create/delete between polls and has bounded latency. Bridge command uses fixed argv and structured stdin, never shell interpolation of Canvas text. No unrequested outbound notification destinations.

## HTTP and client compatibility launch limits

[Official Python SDK releases](https://github.com/modelcontextprotocol/python-sdk/releases) list v2.3.0; its [README](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md) requires Python 3.11+. Pin and install the actual release before relying on APIs. Do not copy v1 FastMCP examples into v2 untested.

The current [MCP transport specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports) and [authorization specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) separate transport from authorization. Canvas OAuth is upstream authorization, not MCP client login. Never accept a Canvas token as an MCP audience token. A private static HTTP credential only works with clients that can configure it; it is not a claim of generic OAuth client compatibility.

Before HTTP support: authenticated access to all data paths, TLS, explicit Host/Origin checks and rebinding protection, audience/issuer validation where OAuth is used, per-user credential ownership, request limits, and tested target-client authentication. A server-wide Canvas credential must never become a multi-user service by accident. For local stdio, keep stdout protocol-clean and test a real client subprocess, shutdown/cancellation, discovery and tool execution against the declared supported protocol versions.

MCP does not guarantee waking an idle agent. Cron invokes an external bridge with its own installed client and explicit authorization. Document that separately from connector operation, and test the bridge against its real host before claiming unattended automation.

## Evidence and next action

No numerical merge score is meaningful for an unimplemented design. The acceptance tests above are recommendations, not passed tests. Implement the shared request policy first, then mocked security/limit tests and a stdio smoke test. Resolve the applicable Instructure approval and institution OAuth deployment before a production launch claim. Live permissions/read-state behavior, packaging installation, external-client compatibility and crash durability remain unverified.
