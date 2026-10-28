# Build map

## Destination

Publish an installable, carefully bounded Canvas MCP connector that a student can
use from their own agent clients. Deliver the auth lifecycle, broad read catalog,
attachments, schedule, a replayable change feed, and maintained open-source
project structure. Live institution compatibility is a separate evidence gate.

## Decisions so far

- [Canvas research](research/canvas.md): reviewed GET routes, permission-respecting
  reads, institution OAuth for other users, personal-token mode for testing.
- [MCP research](research/mcp.md): official Python SDK, local stdio, no service to
  deploy for the default workflow, external scheduler for agent wake-ups.
- Apache-2.0 licensing: permissive reuse with an explicit patent grant.
- No copied private Folava source or assets; use its read-only and provenance
  principles as design inspiration.

## Acceptance gates

- Automated security, pagination, auth, polling, real MCP protocol and wheel checks.
- Independent architecture and implementation review; address material findings.
- Public GitHub source with CI, contribution guidance and accurate install paths.
- Real institution OAuth/token and external Codex/T3 verification are recorded
  separately from mock-backed tests. They require the account owner's consent and
  available institution credentials; never invent successful live validation.

## Out of scope for this release

A hosted multi-tenant SaaS, billing, a web interface, access to locked or external
LTI content, institution-wide Live Events provisioning, and direct execution of
agent commands from untrusted course content. These need separate requirements.
