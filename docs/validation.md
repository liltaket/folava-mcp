# Validation evidence

Local evidence recorded 2026-10-28 on Linux, Python 3.14.4.

| Check | Evidence |
| --- | --- |
| Locked development installation | `uv sync --frozen` completed in a clean project environment. |
| Automated suite | 116 tests passed, including protocol and local TLS fixtures. |
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
