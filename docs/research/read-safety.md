# Read-safety review, 0.1.3

Source inspection and independent Sol review, 2026-10-28. The upstream snapshot
recorded during this review is
[`1c9f0bb`](https://github.com/instructure/canvas-lms/tree/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c).
An institution can run another version or custom hooks. These are bounded
engineering reviews, not a third-party audit or a guarantee of remote invariance.
The findings table records the 0.1.3 boundary; the InstFS follow-up below extends
the attachment destination policy.

## Findings addressed

| Surface | Upstream behavior / evidence | Current boundary |
| --- | --- | --- |
| Assignment detail | `AssignmentsApiController#show` records a read module action. | Excluded. Filter the assignment collection by `assignment_ids[]`. |
| Module-item detail | The Horizon path can record a read action. | Excluded. Use the item collection and select locally. |
| Quiz submissions | Collection reads can schedule overdue grading; detail lookup can repair stored question/submission data. | Both submission routes excluded. Quiz metadata remains available. |
| Submission includes | `read_state` can mark feedback read; excluding only `read_status` was insufficient. | Reject both spellings, including nested/comma-separated values and continuation links. |
| Canvas file download | UI download routes can record progress. `preview=1` does not protect every permission fallback, and a separate file host can reconstruct the user from a verifier. | Never fetch metadata's download URL. Use the permission-checked `public_url` API, then accept direct S3 REST storage only. No Canvas authorization or cookies on storage requests; revalidate every redirect and public DNS address. |
| Page revision detail | The malformed revision-YAML recovery branch can save a repaired record on GET. | Excluded. Revision-list metadata remains available. |
| Page/front-page detail | No page-read-to-module-completion path was found in the inspected upstream versions. A real Canvas requirement comparison nevertheless differed without retaining enough diagnostics to establish kind or cause. | Conservatively excluded pending controlled evidence. Use page collections with body includes where permitted. |
| Module observations | Item collections can evaluate and save outdated derived progress from existing requirements/grades. | Retained as observations, with explicit limits. Do not promise unchanged remote state. |

Primary implementation references:

- [Assignment detail controller](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/app/controllers/assignments_api_controller.rb)
- [Module-item controller](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/app/controllers/context_module_items_api_controller.rb)
- [Quiz-submission controller](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/app/controllers/quiz_submissions_api_controller.rb)
- [Submission serializer](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/lib/api/v1/submission.rb)
- [File controller](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/app/controllers/files_controller.rb) and [storage model](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/app/models/attachment.rb)
- [Page API controller](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/app/controllers/wiki_pages_api_controller.rb)
- [Module model](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/app/models/context_module.rb) and [derived progression](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/app/models/context_module_progression.rb)

## Validation limits

An independent GPT-6 Astra final pass reviewed the changed client, policy,
catalog, authentication defaults and live harness, and ran 152 focused offline
tests. It found no new concrete bypass, credential leak or blocking correctness
defect. It explicitly retained the derived-state and live-invariance limits
below. The lead's complete software and browser evidence is recorded separately
in [validation](../validation.md).

Regression tests demonstrate the local policy, credential isolation and refusal
behavior. They do not establish every GET handler's effects in every Canvas
deployment. Source inspection did not cover all transitive callbacks of all
remaining catalog routes. Ordinary access logs and derived cache writes remain
possible. See the [live test record](../testing.md#limited-deployment-evidence) for the
actual account evidence and the unresolved observation.

Future progress-invariance testing should use a dedicated test course, retain
diagnostic states only in memory, isolate one action at a time and distinguish
completion transitions from metadata or item-membership changes. Do not rerun
known stateful GETs against student work to demonstrate the failure.

## InstFS content follow-up

A bounded authorized deployment sample returned InstFS pointers instead of S3.
An independent Sol source review examined the same pinned snapshot's
[file public_url controller](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/app/controllers/files_controller.rb),
[attachment model](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/app/models/attachment.rb)
and [InstFS integration](https://github.com/instructure/canvas-lms/blob/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c/lib/inst_fs.rb).
The permission-checked pointer uses `Attachment#public_url`, whose InstFS branch
overrides the user with `nil`. The resulting access capability binds an exact
content resource without the UI controller's module-completion path.
Instructure's [domain documentation](https://community.instructure.com/en/kb/articles/485223-canvas-domain-email-and-server-management)
classifies `*.inscloudgate.net` as Canvas file storage.

The new allowance is deliberately narrower than that domain classification:

- Exact host `inst-fs-dub-prod.inscloudgate.net`, HTTPS, canonical UUID and one
  safely encoded filename under `/files/`; reserved routes, ambiguous encodings,
  decoded separators and control characters are refused.
- Exactly one token with the observed HS512 JWT header and claim set
  `{iat, exp, user_id, host, resource, jti}`. Identity/host must be null and the
  resource must equal the raw path. Callback, fallback and session claims fail
  closed. Parsing rejects duplicate keys and bounds token size.
- Only an immediate 302 from that validated endpoint can enter exact host
  `cdn.inst-fs-dub-prod.inscloudgate.net`. The CDN uses a different internal UUID
  but must retain the identical raw filename. Its token has the confirmed header
  `{alg: HS512, typ: JWT, kid: cdn}`, exactly the observed claims
  `{resource, tenant, iat, exp, jti}`, and an exact raw-resource match. The only
  other query field is a bounded media type. A CDN response must be terminal;
  initial CDN pointers and further CDN redirects are refused.
- Existing public DNS pinning, no Canvas authorization/cookies, byte/time limits,
  per-hop validation and signed-URL redaction remain in force.

JWT inspection is a structural policy filter, not local signature verification.
The authenticated Canvas API supplies the original capability; the storage
services verify signatures. The provider's validated redirect supplies the
internal object-ID mapping. CDN routing and claim shapes were observed in the
deployment, not established from public CDN server source. Neither InstFS nor
CDN server internals were available for exhaustive review. Ordinary access logs,
cache writes and undocumented/custom deployment behavior remain possible.
This is evidence for constrained content delivery, not remote-state invariance.

Actual PDF attachments were downloaded through this path and produced text;
a hidden attachment was still refused. Local tests cover token/path/host confusion,
duplicate and identity-bearing claims, CDN entry/redirect restrictions, credential
isolation and output redaction. PDF text extraction itself uses separate bounded
Poppler processes; it does not enable an additional remote read route.
