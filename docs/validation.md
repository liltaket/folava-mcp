# Validation evidence

Local evidence recorded 2026-10-28 on Linux, Python 3.14.4.

| Check | Evidence |
| --- | --- |
| Locked development installation | `uv sync --frozen` completed in a clean project environment. |
| Automated suite | 187 tests passed, including protocol and local TLS fixtures. |
| Static site | 14 generated pages; internal links/anchors and catalog match validated. |
| Chromium interactions | Example tabs/keyboard, copy success/denial, search/details/empty state, docs navigation, 320/390px layout passed. |
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
No real Canvas OAuth consent, OS-keyring/browser integration, live unread-state
comparison, or complete Codex/T3 UI workflow was validated in this session.

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
