# Independent implementation review

Verdict: request changes before production-quality claims. Development-preview policy positioning is accepted; no additional compliance gate proposed. Read-only review of client.py, policy.py, catalog.py, auth.py, config.py and cli.py. No source changes, agents, or remote writes. Checkout has no Git metadata, so no HEAD could be pinned; files may be changing concurrently.

## BLOCKER — decompression happens before the byte bound

`src/folava_mcp/client.py:172`: `response.aiter_bytes(chunk_size=65536)` limits yielded chunks, not HTTPX decoder allocations. HTTPX's gzip decoder calls zlib.decompress without max_length, then its chunker splits the expanded result. A compressed response can exhaust process memory before the configured limit rejects it; the same path handles downloaded files.

Executed deterministic reproduction: custom `httpx.AsyncByteStream` yields one `gzip.compress(b'x' * 20_000_000)` chunk, MockTransport responds with `Content-Encoding: gzip`, then call `_request('https://canvas.example/a', authorize=True, max_bytes=1000)` with tracemalloc enabled. Compressed length: 19,465 bytes; peak traced allocation: 80,069,767 bytes; only afterward raises `too_large`. Payload construction preceded tracing. This defeats a memory-bounded response claim even though returned bytes remain bounded.

Fix with raw streaming plus explicitly bounded decoding, or reject unsupported compressed responses before decoding. Test compressed bombs with a measured allocation/decoder-output bound, not merely the final error code.

## SHOULD-FIX — advertised quiz-submission pagination rejects valid responses

`src/folava_mcp/client.py:245-248` (and merge logic at 232-235): pagination requires the top-level JSON value to be a list, but the catalogued quiz_submissions route returns an object with a `quiz_submissions` list. Official response contract: https://developerdocs.instructure.com/services/canvas/resources/quiz_submissions .

Executed reproduction: MockTransport returns `{"quiz_submissions":[{"id":1}]}` and `Link: <https://canvas.example/api/v1/courses/1/quizzes/2/submissions?page=2>; rel="next"`. Calling `read('quiz_submissions', {'course_id':'1','quiz_id':'2'}, max_pages=2)` raises `pagination: Canvas returned pagination for a non-list response` on page one. Even max_pages=1 cannot return the first page with an incomplete marker. Add operation-specific pagination envelope handling, including associated arrays, and realistic fixtures.

## SHOULD-FIX — authentication accepts origins the data client cannot use

`src/folava_mcp/config.py:29-50` permits and preserves custom HTTPS ports; `src/folava_mcp/policy.py:27` rejects every port except 443. `auth.login_token` / OAuth can verify and persist an origin such as `https://canvas.example:8443`, report successful connection, and then every CanvasClient construction rejects it. Normalize/validate with the same policy before collecting/exchanging credentials. Test onboarding-to-client origin consistency. Private-address restrictions likewise belong in a clear supported deployment contract; this review does not request private-network support.

## Validation and remaining evidence

Ran `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /tmp/folava-build/bin/python -m pytest -q -p no:cacheprovider`: **106 passed, 1 failed**. At execution time `tests/test_server.py:39` accessed `initialized.serverInfo`; installed SDK exposes `server_info`. Parent owns server/events; treat this as observed validation evidence, not a duplicate review assignment. No live Canvas account, TLS handshake, or institutional OAuth exchange tested.

Inspected credential origin/identity binding, serialized refresh and metadata writes, callback state checks, unknown query rejection, conversation read-state enforcement, submission read_status rejection, redirect credential stripping and UTF-8/base64 file reconstruction. No further demonstrated critical defect in those paths. This is not an exhaustive live read-side-effect audit of every Canvas route.

Production transport disables keepalive and serializes requests, avoiding cross-host connection reuse when two hostnames resolve to the same IP. Existing pinning test checks request URL/Host/SNI extension via MockTransport; it does **not** establish actual TLS certificate-name validation through HTTPX/httpcore. Add a real local TLS transport integration fixture with controlled resolver/certificates before claiming that evidence. No pooling defect demonstrated.

Auth uses a separate eager HTTPX client for verification/token responses; data-client response limits do not cover those responses. Current tests should not be described as proving all network responses are bounded.

Next action: repair decoding bounds and envelope pagination, unify origin policy, then rerun targeted tests and parent-owned stdio validation. No numerical merge score: no immutable review point and implementation is being edited concurrently.
