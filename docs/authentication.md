# Connect Canvas

Credentials are configured by a person or a trusted secret injector, outside the
MCP conversation. There is no tool that asks an agent to collect a token.

## Before a real deployment

The current [Instructure API policy](https://www.instructure.com/policies/canvas-api-policy)
section 3(i) explicitly addresses MCP and requires Instructure approval. This
project has not obtained that approval. Its public source and demo are a development
preview, not a claim of an approved or commercially ready Canvas integration.
Confirm the terms and institutional approval applicable to your deployment first.
An OAuth developer key alone does not establish that approval.

Canvas's [OAuth documentation](https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth)
reserves manually generated tokens for development/testing and requires OAuth for
multi-user applications. A free or open-source project is not an exception.

## Institution-managed OAuth

A Canvas Cloud administrator must provision or enable an API developer key, grant
its GET scopes, and register the exact redirect URI. This CLI is a confidential
client for an institution/operator-managed deployment. It does not ship a shared
client secret or provide public desktop app registration.

```sh
folava-mcp auth oauth \
  --url https://school.instructure.com \
  --client-id YOUR_DEVELOPER_KEY_ID
```

Enter the developer key secret at the masked prompt. The browser opens Canvas
consent, then returns to `http://127.0.0.1:8765/callback`. The state is random and
validated. Access token, refresh token and client secret stay in the OS keyring;
profile metadata stores only origin, identity, references and scopes.

Use `--redirect-uri` for another registered loopback port above 1023. This must be
accepted by the specific Canvas deployment; loopback approval is not assumed.
`--no-browser` prints the consent URL, but the callback still has to reach this
computer. It is not a device-code flow or an automatic remote-browser login.

The CLI requests a compact set of documented scopes for common student reads.
The developer key must permit all requested scopes. Extra catalog operations can
require additional scopes: repeat `--scope 'url:GET|/api/v1/...'` to replace the
default set; the profile scope is always added. Use the exact scope strings from
the endpoint's official documentation, whose placeholder names can differ from
our path argument names. Included associations can need additional institution
permissions or key configuration. Scope or permission failures are reported.

Before each MCP operation the credential loader checks expiry and refreshes when
needed. Profile locks serialize refresh across local processes. Tokens are bound
to the canonical origin and verified Canvas user ID. A browser flow, actual
redirect approval and refresh lifecycle still require live institution testing.

## Your own development/testing token

Where your institution permits personal tokens for testing:

```sh
folava-mcp auth login --url https://school.instructure.com --personal-token
```

The token is entered at a masked prompt, verified against the profile endpoint,
and stored in the OS keyring. Do not distribute a workflow asking other students
to generate and paste personal tokens. A token may have write privileges upstream;
this connector's resource boundary remains read-only, but theft of the original
token is a separate risk. Prefer scoped institution credentials.

## Headless testing and managed secret injection

Set `CANVAS_URL` and exactly one of `CANVAS_TOKEN_FILE` or `CANVAS_TOKEN` in the
server's execution environment using your existing secret manager. The former
must point to a regular, non-symlink file owned by you, mode `0600` on POSIX.
Windows operators must restrict its ACL to the service user. No plaintext fallback
is created when the keyring is unavailable. Environment credentials override the
selected profile and are not copied into configuration.

Never paste real token values into MCP JSON, Codex TOML, shell history, issues or
chat. Files and environment credentials also remain secrets outside this package.
The OS-backed stores are Keychain, Windows Credential Manager and Secret Service.
A headless server without one can use a managed secret file for testing; there is
no advertised headless OAuth broker in this release.

## Profiles, diagnosis and removal

```sh
folava-mcp auth status
folava-mcp doctor --profile default
folava-mcp config --profile default
folava-mcp auth logout --profile default
```

Logout removes the local profile and keyring credential. Add `--revoke` to revoke
that credential at Canvas first; other software sharing it will lose access.
Environment/file credentials must be removed from their original secret source.
Revocation failure retains the local credential so the command can be retried.

Configuration defaults to `~/.config/folava-mcp` on Linux,
`~/Library/Application Support/folava-mcp` on macOS and `%APPDATA%/folava-mcp` on
Windows. `FOLAVA_CONFIG_DIR` selects a separate directory. Do not synchronize
keyring databases or resolved credentials through Git.
