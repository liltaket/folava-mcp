# Getting started

You need Python 3.11 or newer and an MCP host that can launch a stdio command.
[uv](https://docs.astral.sh/uv/getting-started/installation/) manages an isolated
tool installation on Linux, macOS and Windows. No Node runtime is required.

## Install

```sh
git clone https://github.com/liltaket/folava-mcp.git
cd folava-mcp
uv tool install .
folava-mcp --help
```

For an immutable installation, check out the release tag before installing, or
install the wheel attached to the GitHub release. Package versions are pinned in
`uv.lock` for development and CI. The application is not claimed to be on PyPI.
To update a source installation, update the checkout and use `uv tool install .
--force`. Review changes before upgrading credentials-handling software.

## Codex

Try the synthetic workspace first:

```sh
codex mcp add canvas-demo -- folava-mcp serve --demo
```

Ask for the demo course's assignments or field guide. Demo dates are fixed sample
data, not relative to today. The process waits for MCP messages when run directly.

After [authentication](authentication.md) and `folava-mcp doctor`:

```sh
codex mcp add canvas -- folava-mcp serve --profile default
codex mcp list
```

If your GUI client cannot find the command, use the absolute executable path
reported by `uv tool dir --bin`. On Windows include `.exe` where required.

The equivalent configuration is available with `folava-mcp config`:

```toml
[mcp_servers.folava]
command = "folava-mcp"
args = ["serve", "--profile", "default"]
```

Codex supports local stdio servers and stores this in its MCP configuration; see
[official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp).
Review the generated snippet and merge it into your existing configuration; the
CLI does not overwrite your file. A `codex mcp login` command authenticates an
HTTP MCP server, not this local server's upstream Canvas connection.

## T3 Code and multiple computers

Configure the Codex provider on the machine where its Codex process executes.
When T3 runs the provider on another linked computer, that computer needs the
executable, credentials and Codex MCP entry. Restart the provider/session after
configuration changes. There is no assumed T3-specific Canvas plugin or automatic
configuration propagation in this release. External T3 UI behavior has not been
validated here; the official SDK protocol test is a separate check.

Repeat installation and institution-approved authentication per computer. Use
separate named profiles for separate accounts. Avoid copying tokens into shared
project configuration. Centralized authenticated HTTP hosting could reduce
per-device setup, but is intentionally outside this release's supported surface.

## Other MCP hosts

`folava-mcp config --format json` prints:

```json
{
  "mcpServers": {
    "folava": {
      "command": "folava-mcp",
      "args": ["serve", "--profile", "default"]
    }
  }
}
```

Merge that entry into a host's supported stdio configuration. Host-specific paths
and approval interfaces vary. The server exposes tools as well as a guide
resource so ordinary workflows do not depend on a resource browser.
