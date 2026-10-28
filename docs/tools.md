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
| `canvas_agenda` | Read planner work and explicit course calendars, both events and assignment dates. |
| `canvas_file` | Read a bounded attachment by Canvas file ID. |
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

## Attachments

`canvas_file` returns UTF-8 text or base64 binary content with MIME, size and SHA-256.
Its default byte limit is 200,000, maximum 500,000. An oversized file produces a
clear error; it is never silently cut into corrupt binary data. A capable host can
consume the base64 payload. No automatic PDF, Office, archive or executable
processing occurs.

For larger attachments, a person can explicitly export a local file:

```sh
folava-mcp file 601 --output field-guide.pdf
```

The CLI defaults to 5 MB and permits at most 20 MB via `--max-bytes`. Existing files
are never overwritten. Parent directories must already exist. Treat exports as
private coursework; do not execute unknown content.

The client reads file metadata, then the fixed `/api/v1/files/{file_id}/public_url`
API pointer. Content requests accept only audited AWS S3 REST destinations and
send no Canvas authorization or cookies. Every redirect must meet that same
policy. The client never follows metadata's Canvas download/preview URL; Canvas
file-host routes, InstFS, CDN, custom endpoints and local-storage fallbacks are
unsupported and refused. A permitted file's metadata does not guarantee its
storage backend is supported. No real attachment content was downloaded in the
recorded Canvas checks.

Signed URLs are not returned by the file tool. Raw API reads can contain upstream
signed URLs—treat those responses as private capabilities and do not log or
publish them.
