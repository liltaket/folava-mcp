# Folava MCP

[![CI](https://github.com/liltaket/folava-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/liltaket/folava-mcp/actions/workflows/ci.yml)

**Your coursework, in the conversation.**

A read-only connection between Canvas LMS and the agents you already use.
Ask about next week's deadlines, read assignment instructions, inspect feedback,
or find a course attachment—without giving an agent the ability to submit work.

[Project site](https://liltaket.github.io/folava-mcp/) · [Getting started](docs/getting-started.md) · [Tools](docs/tools.md) ·
[Authentication](docs/authentication.md) · [Architecture](docs/architecture.md)

**Let your agent set it up.** Copy this into your conversation:

> Set up Folava MCP using https://liltaket.github.io/folava-mcp/install.md.
> Install the published release and connect the demo first, then guide me through
> connecting Canvas. Keep credentials outside this conversation.

The [agent setup guide](docs/agent-setup.md) covers installation, existing MCP
configuration, demo checks and the separate account connection.

```text
You       What do I need for the fieldwork seminar?
Agent     Reads the course outline, assignment and attached field guide.
          Explains the preparation, with the original Canvas links.
Canvas    Stays the source of truth.
```

## Built for the way students work

- **Useful context.** Courses, assignments, your submissions and feedback,
  modules, pages, announcements, discussions, calendars, groups and files.
- **A small tool surface.** Task-shaped tools for common questions; a searchable
  operation catalog for deeper reads, with the original Canvas fields intact.
- **A deliberate read boundary.** Reviewed GET routes, safe read-state settings,
  bounded pagination, permission errors, and protected attachment downloads.
- **Your own environment.** Runs as a local process. No Folava account, hosted
  database, telemetry, model subscription or API key is required.
- **Changes you can automate.** Poll a collection, persist its hashes, and replay
  JSONL events after a cursor. Connect your own scheduler or agent runner.

## Development preview

Instructure's current [API policy §3(i)](https://www.instructure.com/policies/canvas-api-policy)
explicitly addresses MCP and requires its approval. This project has not obtained
that approval. The public source and synthetic demo are available for development;
real deployment and commercial launch have [external gates](docs/release-readiness.md).
OAuth credentials alone do not establish approval.

## Try it without a Canvas account

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
git clone https://github.com/liltaket/folava-mcp.git
cd folava-mcp
uv tool install .
folava-mcp serve --demo
```

The last command speaks MCP over stdio and waits for a client; it is not an
interactive chat. To connect Codex to the synthetic demo:

```sh
codex mcp add canvas-demo -- folava-mcp serve --demo
```

For a real connection, [configure Canvas authentication](docs/authentication.md),
run `folava-mcp doctor`, then:

```sh
codex mcp add canvas -- folava-mcp serve
```

T3 Code's Codex provider uses the MCP configuration of the Codex process on its
execution machine. Install and authenticate on each machine running that process.
See [client setup](docs/getting-started.md) for profiles and other MCP hosts.

**Distribution:** install from this repository or a release wheel. There is no
claimed PyPI publication. The demo uses synthetic course data; real access depends
on your institution, account permissions and OAuth scopes.

## Read-only is enforced

Tool annotations describe the intent; the HTTP boundary enforces it. Agent tools
cannot select an HTTP method, supply an arbitrary destination, submit an
assignment, or run an upload. Conversation reads disable automatic marking as
read. Submission reads reject both `read_status` and `read_state` includes. Known
stateful GET routes and unresolved page-detail reads are excluded; use the
supported collections in the [tool guide](docs/tools.md). OAuth token exchange
and revocation are separate credential operations.

Attachment reads obtain file metadata and the fixed API storage pointer, then
accept only audited AWS S3 REST destinations without Canvas authorization or
cookies. Canvas download/preview routes and other storage backends are refused.
HTTPS, public-address DNS pinning, redirect, byte and time limits still apply.
Credentials stay outside tool arguments and generated client config.

GET does not mean the account is byte-for-byte unchanged: Canvas can record
access logs and refresh derived progress caches. A sampled Canvas progress comparison
was inconclusive; page causality was not established. See the
[validation evidence](docs/validation.md). Viewing content through external clients
can share that content with the model provider you chose. See [security](SECURITY.md)
and [privacy](docs/privacy.md).

## What the boundary means

This connector exposes reviewed reads within your existing permissions. It cannot
unlock unpublished courses, recover hidden grades, read other students' private
work, or extract arbitrary external LTI data. Its calendar reflects what is
published in Canvas, not necessarily your university's entire timetable.

Canvas OAuth requires a developer key enabled by your institution. Personal token
mode exists for your own development and testing; it is not the onboarding flow
for a multi-user commercial service. [Why this matters](docs/authentication.md).

A running MCP server does not wake a closed agent. The change feed is designed for
an external scheduler. Institutional Live Events is a separate administrator
integration, not a promised student capability.

## Develop

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build
```

Build the documentation site with `uv run python scripts/build_site.py`.
See [site development](docs/site.md) for browser checks and deployment.

The suite includes real MCP stdio handshakes against synthetic data, hostile URL
and query cases, pagination, authentication, attachment boundaries and durable
polling. Mock-backed checks are distinct from live institution and client testing;
see [validation](docs/validation.md) and the [testing guide](docs/testing.md).

[Contributions](CONTRIBUTING.md) are welcome. Read-only safety and clear error
reporting are release requirements. Inspired by the student-first principles of
Folava; implemented independently without its private source or assets.

Licensed under [Apache-2.0](LICENSE). Independent project; not affiliated with
Instructure. Canvas is a trademark of Instructure, Inc.
