# Read-safety review, 0.1.3

Source inspection and independent Sol review, 2026-10-28. The upstream snapshot
recorded during this review is
[`1c9f0bb`](https://github.com/instructure/canvas-lms/tree/1c9f0bb8013ed69c4f2efe11fd483025469b7e6c).
An institution can run another version or custom hooks. These are bounded
engineering reviews, not a third-party audit or a guarantee of remote invariance.

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
