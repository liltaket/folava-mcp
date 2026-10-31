# Canvas API research — 2026-10-28

> Historical research note: current implementation excludes assignment/module-item
> detail, quiz-submission, direct page/front-page and individual revision reads.
> Attachment content now requires the fixed public_url API pointer and audited
> S3 or the reviewed InstFS content path. See the [current tool boundary](../tools.md#excluded-reads)
> and [validation evidence](../validation.md); older candidate routes below are
> not an instruction to call them.

## Recommended architecture

A local-first MCP server over stdio is the smallest reliable deployment for students' own agent clients. Separate a narrowly audited GET-only Canvas transport, resource tools, credential lifecycle, and a polling change feed. Keep credential setup outside model-visible tool arguments. Offer per-machine authentication rather than distributing one credential in client configs. A hosted multi-user variant needs institution OAuth developer keys and an actual authenticated MCP perimeter; do not present an unauthenticated HTTP server as cross-device convenience.

This is a design recommendation, not a capability promised by Canvas.

## Authentication and product constraint

Canvas explicitly reserves manual access-token generation for development/testing; requesting another user's manually generated token violates its API policy, and multi-user apps must use OAuth. Canvas Cloud institution administrators issue developer keys (client ID and secret). Tokens should use secure local storage, ideally OS keychains, and Authorization headers, never query strings. Personal testing can accept a token from an environment or protected file, but this is not a policy-compliant commercial onboarding plan. A reusable open-source self-host mode can support institution-provided keys; a maintained commercial service must secure appropriate keys and review the API policy.

Source: https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth

OAuth authorization-code exchange requires client ID and secret. Default current developer keys yield access tokens expiring after one hour, with refresh tokens. Request endpoint-specific GET scopes on a scoped developer key. Request multiple scopes as one space-separated parameter. A client-credentials token is for IMS/LTI scopes, not a substitute for arbitrary student REST API access. OAuth state must be random and checked. Do not use replace_tokens=1 when adding a device, since it destroys existing tokens. Do not assume Canvas supplies device-code flow, dynamic registration, or public-client PKCE just because MCP does.

Source: https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth_endpoints

## Read-only means more than HTTP GET

GET /api/v1/conversations/:id defaults auto_mark_as_read=true. Always force auto_mark_as_read=false in the transport, including pagination links and raw query input; reject attempts to override it. Lists alone do not fetch full bodies.

Source: https://developerdocs.instructure.com/services/canvas/resources/conversations

Submissions include[]=read_status explicitly marks submissions as read. Reject it in every query representation, including bare include, bracketed/indexed include keys, repeated values, and pagination URLs. Avoid UI preview URLs to fetch submission annotations: viewing annotations in Canvas web automatically marks them read. Legitimate read paths include assignment detail, own submission detail, and optional submission_comments, rubric_assessment, submission_history. Submission URL user_id is the student ID; it is not a separate submission identifier.

Source: https://developerdocs.instructure.com/services/canvas/resources/submissions

Module items have explicit POST mark_read, and html_url redirects normally fulfill must-view requirements. Fetch resource API URLs, not arbitrary UI html_url navigation. Large modules can omit requested inline items, so use the item-list API rather than assuming include[]=items is complete.

Source: https://developerdocs.instructure.com/services/canvas/resources/modules

Do not offer an unrestricted arbitrary-URL GET tool. Use reviewed endpoint templates with endpoint-specific query rules and explicit excluded action paths. Add an extension registry so API breadth can grow without weakening the boundary. Reject absolute URL, dot-segment, percent-encoded separator, scheme-relative URL, method override, as_user_id impersonation, and query access_token inputs. Canvas will still record normal server access logs; promise no intentional learning-content mutations rather than zero server-side traces.

## Calendar and planning

GET calendar_events defaults to the current user's PERSONAL calendar, excluding course/group calendars. Pass context_codes[] explicitly, up to 10 per request; batch larger sets. type defaults event, while type=assignment returns assignment deadlines. A full schedule queries both. start_date/end_date/all_events control the window; unbounded sync should be opt-in. Preserve timezone offsets and all_day_date.

Source: https://developerdocs.instructure.com/services/canvas/resources/calendar_events

GET /api/v1/planner/items provides a student-oriented mixed agenda with optional date bounds and new_activity filter. It defaults to all associated contexts; concluded courses need explicit include. Planner overrides are user settings and should never be mutated. Use planner as convenient agenda, resource detail for authoritative assignment/submission information; do not claim planner is every historical object.

Source: https://developerdocs.instructure.com/services/canvas/resources/planner

## Pagination and rate limits

Canvas lists default to 10. per_page has an unspecified server maximum: never infer completeness from page size. Follow Link rel=next as opaque, absolute URLs and read header names case-insensitively. The last relation can be absent. Locally constrain origin, scheme and path before following any link, preserving endpoint safety rules; bound pages/items/bytes and expose truncation and next cursor.

Source: https://developerdocs.instructure.com/services/canvas/basics/file.pagination

Canvas throttles by request cost and replenishing quota rather than a universal fixed request-per-second allowance. Read X-Request-Cost and X-Rate-Limit-Remaining. 429 means back off. Parallel requests incur extra pre-flight penalty; serialized/low concurrency requests are a sound default. Implement bounded retry with timeout, capped Retry-After, and cancellation.

Source: https://developerdocs.instructure.com/services/canvas/basics/file.throttling

## Attachments and downloads

Files expose size, MIME type, lock status, download URL and optional user-specific preview URL. File access remains subject to current Canvas permissions; metadata URL does not guarantee downloadable content. File public_url can return a presigned storage URL: treat it as a secret capability. Attachment links may lead to storage outside Canvas. Fetch metadata by ID, follow HTTPS redirects manually with a strict hop/byte/timeout bound, never forward Canvas authorization to another origin, and block private/loopback/link-local destinations and DNS rebinding. Preserve filename safely; do not trust server-provided paths. Return small text or bounded binary MCP resources; do not execute attachments. Never place transient signed URLs in logs or durable event state.

Source: https://developerdocs.instructure.com/services/canvas/resources/files

## Events and agent wake-ups

Canvas Live Events supports AWS SQS or HTTPS webhook destinations, but its own documentation says it is for analytics rather than immediate authoritative freshness. Use REST reconciliation after an event.

Source: https://www.k12.instructure.com/doc/api/file.data_service_introduction.html

Data Services configuration is an account permission exposed in Admin navigation. An ordinary student token cannot provision institutional Live Events. Production and Beta supported, not Test. Therefore baseline is permission-respecting REST polling with persisted snapshot hashes and a durable event cursor. Emit created/changed/deleted only after a COMPLETE successful collection; never infer deletion from an error, pagination cap, or lost permission. First run should establish a baseline (optionally explicit initial events). A process must remain running or be scheduled by the user; MCP alone does not independently wake a sleeping agent. Give JSONL output or a local webhook adapter to an external scheduler, keeping outbound delivery opt-in and credentials separate.

Source: https://community.instructure.com/en/kb/articles/661440-unknown

## Coverage and honest claims

Expose courses/enrollments, assignments and own submissions/feedback, modules/items, pages, files/folders, announcements/discussions, planner/calendar, profile, groups and conversations. Discover more reviewed GET routes through a catalog. Canvas permissions still apply; closed/unpublished/locked courses, other students' submissions, or external LTI tool data may not be available. A Canvas API bridge cannot promise access to every institutional timetable or every external platform attachment. Calendar reflects what the institution actually publishes in Canvas.

## Concrete verification requirements

- Test zero non-GET calls on the resource transport (OAuth token POST is separate lifecycle and excluded from agent tools).
- Test conversation auto-read override and submission read_status rejection in named tools, generic GET and pagination.
- Test hostile pagination origin and path, duplicate query variants, credential leaks in exception/log output.
- Test cursor completeness at page cap and malformed Link; 429 retry bounds and timeout cancellation.
- Test calendar contexts above ten and both event/assignment types.
- Test file redirect credential stripping, signed URL redaction, local IP/DNS block, size enforcement while streaming.
- Test polling restart deduplication, stable baseline, failed/incomplete polls causing no deletes, scope/account identity separation.
- Test MCP client initialize/list/call over stdio and graceful shutdown. Live institution OAuth, exact endpoint permissions and external client setup remain separate acceptance evidence requiring real accounts.
