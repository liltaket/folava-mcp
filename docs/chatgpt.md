# Use Folava in ChatGPT

Connect Folava's tools to a ChatGPT web conversation through a private MCP
tunnel. Folava runs on your computer; the project website is documentation,
not a server URL to enter in ChatGPT.

This recipe follows current OpenAI documentation. A complete Folava connection
and tool call in ChatGPT have not yet been verified.

## 1. Start with the demo

[Install the published release](agent-setup.md#2-install-the-release).
The first connection uses `folava-mcp serve --demo`: fictional coursework,
with no Canvas credentials or Canvas requests.

You need permission to add custom MCP plugins in ChatGPT and to create/use a
Platform tunnel. Availability depends on your account and workspace.

## 2. Connect a private tunnel

In [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels),
use your personal Platform organization and associate the tunnel with your
personal ChatGPT workspace. Creation needs **Tunnels Read + Manage**; runtime
access needs **Read + Use**. Keep access limited to yourself before connecting
Canvas; a shared workspace association can give others a path to this process.

Install OpenAI's `tunnel-client` using its
[official tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
Supply a restricted runtime key as `CONTROL_PLANE_API_KEY` through your local
secret manager. This is an OpenAI key, separate from Canvas credentials.
Keep literal keys outside chat, shell history and configuration files.

Replace `YOUR_TUNNEL_ID` with the ID from settings. Use an unused profile name:

```sh
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile folava-demo \
  --tunnel-id YOUR_TUNNEL_ID \
  --mcp-command "folava-mcp serve --demo"
tunnel-client doctor --profile folava-demo --explain
tunnel-client run --profile folava-demo
```

If needed, use Folava's full executable path from `uv tool dir --bin`, including
`.exe` on Windows. Run both processes as the user who installed Folava.

Leave the client running. This route uses an outbound connection without a
public Folava listener. See the official guide for platform-specific setup.

## 3. Add it to ChatGPT

In [ChatGPT Plugins](https://chatgpt.com/plugins):

1. Select **+**, then **Add custom MCP server**.
2. Name it **Folava demo**, choose **Tunnel** under Connection and select your tunnel.
3. For this local stdio connection, choose **No authentication**. Access is
   controlled by the private tunnel; this is separate from Canvas sign-in.
4. Review the warning, create it under your personal plugins and install it.

In a new conversation, type `@`, select **Folava demo**, and ask:

> Use Folava demo to list my courses with canvas_courses.

Expect fictional course `ENV101`. Confirm an actual tool response, rather than
just a successful plugin installation. The
[OpenAI connection instructions](https://developers.openai.com/api/docs/guides/custom-mcp-server)
describe the current controls.

## 4. Connect your Canvas account

Read the [Canvas authentication guide](authentication.md) first, including the
approval and institution requirements. Authenticate privately and run:

```sh
folava-mcp doctor --profile default
```

Stop the demo tunnel client. Create a separate tunnel-client profile using the
same tunnel ID, changing the profile name to `folava-canvas` and the MCP command
to `folava-mcp serve --profile default`. Run its doctor check, then start it.
Rename the personal ChatGPT plugin to **Folava** and refresh its tool list.

Folava enforces the same reviewed read boundary as in other MCP hosts. Keep
both tunnel and plugin access limited to your own account: callers use the
Canvas profile available to that process. Course results sent into ChatGPT are
subject to OpenAI's data terms; see [data handling](privacy.md).

## If it does not connect

- **Tunnel missing:** check its workspace association and your Use permission.
- **Tool discovery fails:** keep the host awake and the client running; check
  `tunnel-client doctor --profile folava-demo --explain` (or `folava-canvas`).
- **Demo works, Canvas fails:** run Folava's doctor as the same OS user. Check
  that the real profile, executable path and credential store are available.

Stopping the tunnel client stops this connection. Remove the plugin and tunnel
when no longer needed; these steps do not revoke a Canvas credential.

## Using the desktop app

The [official MCP settings guide](https://learn.chatgpt.com/docs/extend/mcp)
also describes local servers in the ChatGPT desktop app: **Settings → MCP
servers → Add server**, choose **STDIO**, command `folava-mcp`, arguments
`serve --demo`, then save and restart. Type `/mcp` to check the connection.
After authentication, use `serve --profile default` for Canvas.
