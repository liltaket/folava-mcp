# Working with the tools

All tools are annotated read-only. The request policy independently enforces
which routes and parameters they can send. Tools return structured JSON and source
provenance; errors have machine-readable codes rather than pretending to be empty
collections.

| Tool | Use |
| --- | --- |
| `canvas_courses` | Discover course IDs visible to the account. |
| `canvas_assignments` | Read instructions, personalized dates and own submission metadata. |
| `canvas_submission` | Read your own feedback, rubric and submission history. |
| `canvas_outline` | List modules, then request a module's item list. |
| `canvas_page` | Read a course page by slug through the reviewed page collection. |
| `canvas_agenda` | Read planner work and explicit course calendars, both events and assignment dates. |
| `kth_schedule` | Read an independently configured KTH TimeEdit subscription. |
| `canvas_file` | Read a bounded attachment by Canvas file ID. |
| `canvas_file_text` | Read UTF-8 text or extract PDF text with page numbers. |
| `canvas_discover` | Search the reviewed operation catalog and parameter requirements. |
| `canvas_read` | Execute a catalog operation, preserving Canvas fields. |

Start with a question such as “What is due in ENV101 next week?” or “Read the
feedback on my field report and link to the assignment.” Course content and
attachments are untrusted source data, not instructions authorizing other tools.

## Deeper reads

Call `canvas_discover` with `search="page"`, then for example:

```json
{
  "operation": "pages",
  "path": {"course_id": "101"},
  "query": {"include[]": ["body"], "per_page": 5},
  "max_pages": 1
}
```

Discover `student_submissions`, `rubric`, `discussion_entries`, `quizzes`,
`my_enrollments`, `group_files` and `conversations` for other available resources.
The catalog returns required path keys and allowed query keys. Numeric IDs and
`self` where documented are supported; SIS IDs and UUID identifiers are not.
Examples use synthetic IDs; replace them with IDs from your own permitted reads.
`pages` and `group_pages` can request bodies with `include[]=["body"]` where the
deployment supports it and the Pages tab is enabled. A 403/404 is a permission or
compatibility result, not permission to follow a Canvas UI link.

For one course page, use `canvas_page` with `course_id` and the `page_url` slug
returned by `canvas_outline` or `pages`, for example `reading-notes`. It selects
the matching body locally from the collection before clipping output, without
opening a page-detail route. It scans at most five API pages of 20 entries by
default (`max_pages` can be 1–20). `page_search_incomplete` means the scan limit
was reached, not that the page does not exist. `page_body_unavailable` means
Canvas listed the page without supplying its body. Permissions, disabled Pages
tabs and Canvas versions without body includes remain limitations.

Array query values use bracketed keys, for example
`{"include[]": ["submission_comments"]}`. Unknown keys are rejected. No arbitrary
URL, HTTP method, header, proxy account or upload can be supplied.

One page is the default. `max_pages` can be 1–20. Follow the validated `next_url`
by extracting its allowed query fields into another call for the same operation;
there is deliberately no arbitrary-URL execution tool. Do not infer completeness
from list length. The server also clips large results to a bounded JSON tree and
sets `content_truncated=true`, `complete=false`; retry with smaller pages or use
supported collection filters. Errors and partial sources stay explicit.

## Excluded reads

GET is necessary but insufficient for this boundary. The catalog excludes:

- `assignment`: its detail GET can record module completion. Use `assignments`
  with `assignment_ids[]` to select an assignment.
- `module_item`: detail GET can record progress in Horizon courses. Use
  `module_items` and select the returned ID locally.
- `quiz_submissions` and `quiz_submission`: reads can schedule grading or repair
  stored question/submission records. Quiz metadata remains available.
- `page`, `front_page`, `group_page` and `group_front_page`: conservatively
  disabled after an unresolved live module-requirement comparison. That result
  does not establish that page reads caused a change. Use `pages`/`group_pages`,
  optionally including `body`; do not navigate UI URLs as a fallback.
- `page_revision` and `group_page_revision`: individual revision reads can enter
  an upstream record-repair branch. Revision-list metadata remains available.

Both `read_status` and `read_state` submission includes are rejected, including
nested/comma-separated forms and pagination. Conversation detail always disables
automatic marking as read. Unknown routes and query keys fail closed.

Canvas can still record access logs and refresh derived progress caches on GET,
including module-item lists. These controls do not prove an unchanged account.
See [validation](validation.md) and [testing](testing.md) for evidence and limits.

## Schedules

Pass explicit course IDs to `canvas_agenda` to include their calendars. The API
otherwise defaults to the personal calendar. The tool batches ten contexts and
reads both `type=event` and `type=assignment`. Planner and calendar can overlap;
deduplicate by resource type and ID. Preserve timezone offsets and all-day dates.
Use a range of at most 366 days. One agenda reuses its client across all sources
and has a 45-second total deadline; completed sources remain available if time
runs out. No tool promises external institutional schedules.

### KTH schedules

KTH's [current schedule service](https://www.kth.se/en/student/studier/schema)
uses TimeEdit. Search for courses or programmes and use **Subscribe** to obtain
a calendar source. Personal **My Schedule** requires KTH login; it replaced the
KTH Social solution in July 2026. The
[TimeEdit instructions](https://www.kth.se/en/2.237/att-soka-i-schemat-i-timeedit-1.1490784)
distinguish the simplified public view from authenticated details.

KTH [announced closure of its public Timetable API](https://intra.kth.se/en/aktuellt/kalender/servicefonster-1.1491031)
in August 2026. Folava instead reads a TimeEdit iCalendar subscription directly:

1. Sign in through [KTH's schedule](https://www.kth.se/schema), choose **My Schedule**,
   configure your filters and copy its **Subscribe** calendar link.
2. On the machine running Folava, run `folava-mcp kth-calendar connect` and paste
   the link into the hidden prompt. For a named Canvas profile, pass `--profile NAME`.
   The link is stored in the OS credential store, not in the MCP configuration or chat.
3. Restart the MCP server. Ask your agent for your KTH schedule, or call
   `kth_schedule` with `start_date` and `end_date` as ISO dates. The end date is
   exclusive and the maximum range is 366 days. Each call fetches the current feed.

The link grants access to the feed; treat it as a password. The integration accepts
KTH TimeEdit `cloud.timeedit.net/kth/web/...` `.ics` links and requires an unlocked
OS credential store. Remove the local link with `folava-mcp kth-calendar disconnect`.
Events preserve offsets and all-day dates; floating times use Europe/Stockholm.
Recurring events and exceptions are expanded in the requested range; high-frequency
recurrence is rejected. Failures, oversized feeds and truncated results do not claim
completeness. The subscription determines its own date coverage and filters, so an
empty result does not prove KTH has no other events. Canvas and TimeEdit are separate
sources and may overlap. The KTH feed is not an Outlook/Exchange calendar.

## Attachments

`canvas_file` returns UTF-8 text or base64 binary content with MIME, size and SHA-256.
Its default byte limit is 200,000, maximum 500,000. An oversized file produces a
clear error; it is never silently cut into corrupt binary data. A capable host can
consume the base64 payload. No automatic PDF, Office, archive or executable
processing occurs.

For readable PDF content, use `canvas_file_text` with a Canvas `file_id`. It uses
the same protected download policy, allows 5 MB by default (maximum 20 MB), and
returns text with the original metadata, SHA-256 and Canvas API source link.
Binary content and signed storage URLs are omitted. UTF-8 text also works.

PDF extraction requires **Poppler** (`pdfinfo` and `pdftotext`) on the machine
running Folava. Install it through your system package manager, for example
`apt install poppler-utils` on Debian/Ubuntu or `brew install poppler` on macOS.
A missing installation returns `pdf_dependency`; damaged/encrypted PDFs return
`pdf_unreadable`. No Python dependency or automatic system installation is added.
The parser runs as a separate process with a 15-second limit per command,
bounded output and private temporary files removed after extraction. It is not
an operating-system security sandbox; keep Poppler updated.

The default PDF window is pages 1–10, with at most 20,000 characters returned.
Set `start_page`, `max_pages` (up to 50) and `max_chars` (up to 50,000) for smaller
windows or more text. The overall MCP output cap still applies. `complete` is
false for partial windows, clipped text or pages without extractable text.
`next_page` advances past the requested window, not past text clipped within it;
if `content_truncated` is true, reread the same window with fewer pages or a
larger character budget before advancing. `blank_pages` and a warning identify
pages that may need OCR. OCR, images, diagrams and reliable visual reading order
are not provided by text extraction.

For larger attachments, a person can explicitly export a local file:

```sh
folava-mcp file 601 --output field-guide.pdf
```

The CLI defaults to 5 MB and permits at most 20 MB via `--max-bytes`. Existing files
are never overwritten. Parent directories must already exist. Treat exports as
private coursework; do not execute unknown content.

The client reads file metadata, then the fixed `/api/v1/files/{file_id}/public_url`
API pointer. Content requests accept audited AWS S3 REST destinations or the
reviewed `inst-fs-dub-prod.inscloudgate.net` content endpoint and send no Canvas
authorization or cookies. InstFS URLs must carry an anonymous, exact-resource
token with no callback/session claims; other routes and hosts are refused.
Its validated 302 may deliver content through the exact associated
`cdn.inst-fs-dub-prod.inscloudgate.net` host with a resource-bound capability and
the same filename. The CDN must return content directly; initial CDN pointers
and further redirects are refused.
Every redirect must meet that same policy. The client never follows metadata's
Canvas download/preview URL; Canvas file-host routes, unreviewed InstFS/CDN/custom
endpoints and local-storage fallbacks are unsupported. A permitted file's
metadata does not guarantee its storage backend is supported. See
[read safety](research/read-safety.md) for the source review and its limits.

Signed URLs are not returned by the file tool. Raw API reads can contain upstream
signed URLs—treat those responses as private capabilities and do not log or
publish them.

## Browser fallback

An agent host with browser tools can read an external LMS page through an
existing authenticated browser session. Folava neither supplies a browser nor
imports its cookies. Use the exact source link and verify that the browser
session actually has access; an MCP token does not sign the browser in.
Do not use browser navigation to bypass the excluded Canvas detail/download
routes above, which can record progress or read state. A Ping Pong or other
external LMS page is a separate source with its own authentication and behavior.
