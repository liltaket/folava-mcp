# Validation evidence

Evidence recorded 2026-10-28. Current 0.1.3 local evidence on Linux,
Python 3.14.4:

| Check | Evidence |
| --- | --- |
| Automated suite | 247 tests passed, including the stricter GET boundary, storage and live-harness diagnostics. |
| Static checks | Ruff lint/format and Git whitespace checks passed. |
| Static site | 15 generated pages and 94 registry-derived operations; internal links and catalog match checked. |
| Chromium interactions | System/light/dark themes, persistence, blocked storage, pre-paint initialization, no-JS fallback, contrast, reduced motion, keyboard, copy, search and 320/390px layouts passed. |
| Dependency advisories | `pip-audit` reported no known vulnerabilities in 45 locked runtime dependencies selected on Linux. This is a dated advisory check, not a security guarantee. |
| Independent review | Sol source review identified GET side effects; Astra's final pass found no new concrete bypass. See [read safety](research/read-safety.md). |
| Distribution | Wheel and source distribution built; the wheel installed outside the checkout and passed version/catalog checks, an official SDK stdio read and excluded-operation refusals. |

The following table preserves the earlier 0.1.2
software/site baseline on Linux, Python 3.14.4; it is not a test count for
later safety changes. Current scenarios and optional live commands are in the
[testing guide](testing.md).

| Check | Evidence |
| --- | --- |
| Locked development installation | `uv sync --frozen` completed in a clean project environment. |
| Automated suite | 187 tests passed, including protocol and local TLS fixtures. |
| Static site | 14 generated pages; internal links/anchors and catalog match validated. |
| Chromium interactions | Example tabs/keyboard, copy success/denial, search/details/empty state, docs navigation, 320/390px layout passed. |
| Hosted CI | All six platform jobs passed on [c411188](https://github.com/liltaket/folava-mcp/actions/runs/40761276825), including Windows refresh concurrency and macOS callback tests. |
| Public site | Real-network Chromium checks passed for the deployed homepage, tabs, catalog and guide in mobile layout. |
| Static checks | Ruff lint and formatting passed. |
| Distribution build | Wheel and source distribution built successfully. |
| Standalone wheel | Installed outside the source tree; CLI help and official SDK stdio course call passed. |

The suite checks policy bypasses, unsafe pagination, protected read-state query
settings, DNS pin construction, real TLS certificate-hostname validation at a
controlled local listener, cross-origin authorization stripping, byte limits,
compression rejection before decoder allocation, OAuth state/refresh, profile
locking, file export, baseline/replay and overlapping-poll rejection.

The TLS fixture substitutes a controlled resolver and port; it exercises the real
HTTPX/httpcore TLS handshake and rejects a mismatched certificate. It is not a
live connection to Canvas or an external storage service. The protocol fixture
starts a real subprocess with the official SDK against synthetic course data.

Independent Sol and Astra reviews are preserved under [research](research/).
Their reports describe the code at their review points. Findings were addressed:
structured MCP output/SDK attributes, aggregate output budgets, poll ordering,
replay limits, encoded response allocation, quiz-envelope pagination and consistent
HTTPS-port policy. Regression tests cover the fixes. No report is an exhaustive
security audit or institutional authorization.

The CI workflow runs the suite and package smoke on Linux Python 3.11–3.14, Windows
3.14 and macOS 3.14. Workflow configuration alone is not evidence all runs passed;
check the [actual GitHub run](https://github.com/liltaket/folava-mcp/actions/workflows/ci.yml).
The checks above do not establish real Canvas OAuth consent,
OS-keyring/browser integration, live unread-state invariance, or a complete
Codex/T3 UI workflow. The bounded real-account evidence below is separate.

The 0.1.1 hardening pass adds real localhost OAuth callback exchanges, forged and
malformed callbacks, partial-request deadlines, concurrent refresh, failed secret
and metadata writes, SQLite transaction rollback, semantic URL changes, cancellation
and stream cleanup, partial download rejection, strict JSON and Link parsing, and
DNS multicast checks. Demo safety/date/file behavior and aggregate agenda deadlines
have independent regressions. All use fixtures and test secrets.

The independent [0.1.1 review](research/v011-review.md) found a release/deployment
ordering hazard; the explicit published-release manifest and deployment-time
installer check address it. The parent ran Chromium checks with the web tools
installed; the review report correctly distinguishes its own environment limits.

Hosted Windows/macOS execution exposed two further authentication issues after
the 0.1.1 local pass: Windows lock-byte initialization before lock acquisition,
and reverse DNS during numeric loopback server startup on macOS. Version 0.1.2
removes both dependencies. The no-DNS regression is deterministic locally; the
concurrent-refresh test exercises the Windows lock behavior on Windows CI.

## Read-safety follow-up and real-account sample

A subsequent source review identified stateful GET behavior in assignment detail,
Horizon module-item detail and quiz-submission routes, plus both submission
read-state include spellings. Those routes/includes are now excluded. Attachment
content now uses metadata and the fixed `public_url` API pointer, allowing only
audited AWS S3 REST destinations without Canvas authorization or cookies. UI,
InstFS, CDN, custom and local-storage fallback downloads are refused.

Limited private checks exercised permitted reads and stdio. A module comparison was inconclusive; its type and cause were not established. Institution and account details are omitted.

Canvas may update ordinary access logs and refresh derived progress caches even
on GET. These samples are not a complete account crawl or proof of an unchanged
account. See [testing](testing.md#limited-deployment-evidence) for the scenario bounds,
credential handling and remaining evidence gaps.
