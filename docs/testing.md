# Testing your connection

Start with deterministic checks and the synthetic demo. Live checks are optional,
use only an account you are permitted to test, and do not establish institutional
approval. The [release gates](release-readiness.md) still apply.

## Scenario coverage

| Scenario | Deterministic check | Optional live acceptance |
| --- | --- | --- |
| Request boundary | Reject unknown methods/routes/keys, disabled operation IDs, unsafe pagination and both read-state include spellings before networking. | A forbidden operation is rejected locally; never provoke a known stateful GET remotely. |
| Course context | Named tools and generic reads preserve provenance, permission errors, completeness and bounded output. | Sample profile, courses, assignments, modules, own feedback, dated planner/calendar and announcements; report status/shape/count only. |
| Pages | Direct page/front-page and individual revision reads are excluded; collections accept optional body includes. | Sample `pages` with `include[]=["body"]` only where supported; retain 403/404 as a limit and stop instead of following UI links. |
| Progress observations | Classify item membership, explicit completed-state and requirement-metadata differences separately; do not equate GET with account invariance. | Isolate one action per comparison in an appropriate test course. An aggregate observation is not causal evidence. |
| Attachment metadata/content | Fixed metadata + `public_url` API path; reviewed S3/InstFS destinations and constrained terminal CDN delivery; no storage authorization/cookies; DNS/TLS, redirects, bytes and deadlines enforced. | Metadata first. Content requires separate opt-in and a supported small file; Canvas UI, unreviewed hosts/routes and local storage remain refused. |
| PDF text | Real synthetic PDFs when Poppler is installed; text, page windows, blank pages, parser errors, deadlines, cancellation and output caps. | Separately verify an accessible PDF download and text result; do not confuse text extraction with OCR or complete visual coverage. |
| MCP protocol | Official SDK initializes a real stdio subprocess and calls tools against synthetic data. | Separately verify a real configured stdio process can initialize, discover tools and read a permitted resource. Host GUI behavior is a separate check. |
| Site | Build/link checks plus Chromium keyboard, themes, storage failure, reduced motion and mobile layouts. | Check the deployed artifact separately from the local build. |

Run the local checks from the checkout:

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python scripts/build_site.py
uv sync --frozen --group web
uv run python scripts/check_site.py
```

The browser check requires the Playwright Chromium installation. See
[site development](site.md) for setup. CI uses fixtures and needs no live Canvas
credentials. Do not substitute success in fixtures for evidence about a real
institution, OAuth consent or account state.

## Opt-in live sample

`scripts/check_canvas.py` accepts a protected token-file path, never a token value
in command arguments. Use a file provided by your existing secret mechanism: a
regular non-symlink file owned by you, mode `0600` on POSIX, or a restricted user
ACL on Windows. Do not paste the value into a command, transcript or issue.

```sh
uv run python scripts/check_canvas.py \
  --origin https://school.instructure.com \
  --token-file /absolute/path/to/protected-token
```

This command uses the supplied credential directly; it does not log in, refresh,
revoke or write a keyring profile. It makes bounded GET requests through the
production DNS/TLS policy, refuses Canvas UI routes and non-GET requests, and
stops at 40 network requests or the 180-second overall deadline. Most direct
scenario reads use one page of at most five items; named tools retain their own
bounded pagination within the same request budget. It samples one course rather
than crawling the account. Results report technical summaries without coursework,
raw IDs, credentials or signed URLs. Permission errors, partial results and
skipped scenarios are evidence limits, not a successful empty account.

Attachment content is skipped by default. To opt in for one accessible file of
at most 200,000 bytes, append `--download-small-file` to the same command. The
script does not save the file or print its content. Unsupported storage fails
closed; do not work around it with a browser/download URL. Even a successful
content check proves only the sampled storage path, not every attachment backend.

Canvas can write normal access logs and refresh derived progress caches during
GET requests. Do not use this harness to promise an unchanged account. Do not
repeat direct page or revision reads to reproduce the unresolved signal below.

## Limited deployment evidence

Private, bounded checks exercised profile/course context, assignment collections,
module and item lists, own submission feedback, planner/calendar, announcements
and named MCP tools. A separate official SDK stdio process initialized,
discovered eight tools, read a permitted resource and rejected an excluded
operation locally. No credentials or upstream payloads are included here.

One aggregate module-requirement comparison was inconclusive. The original
comparator did not retain enough detail to distinguish membership, completion
and requirement-metadata differences. Neither the kind of change nor its cause
was established. Direct page reads were stopped and conservatively excluded.
The offline diagnostic repair does not recover the missing live evidence.

Institution, account, origin, resource IDs, timing, response counts and resource
samples are deliberately omitted from the public record. No complete account
crawl, real attachment-content download, institution OAuth consent/refresh,
full Codex/T3 GUI workflow, or proof of unchanged account state was established.
Inspected upstream source is evidence for the conservative route restrictions,
not proof of any particular institution's deployed build or custom hooks.
