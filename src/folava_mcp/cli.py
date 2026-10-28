"""Human-facing setup and automation commands; stdout stays clean in serve mode."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Annotated, Any

import typer

from . import auth
from .client import CanvasError
from .config import ConfigError, config_dir, list_profiles, validate_profile_name

app = typer.Typer(
    no_args_is_help=True,
    help="Read Canvas from your agent. Configure once, then connect over MCP.",
    pretty_exceptions_enable=False,
)
auth_app = typer.Typer(
    no_args_is_help=True, help="Connect Canvas without exposing credentials to your agent."
)
app.add_typer(auth_app, name="auth")
events_app = typer.Typer(no_args_is_help=True, help="Replay locally recorded change events.")
app.add_typer(events_app, name="events")

ProfileOption = Annotated[str, typer.Option("--profile", "-p", help="Canvas profile name.")]
# Small enough for institutional consent URLs; expanded access is opt-in with --scope.
DEFAULT_SCOPES = [
    "url:GET|/api/v1/users/:user_id/profile",
    "url:GET|/api/v1/courses",
    "url:GET|/api/v1/courses/:id",
    "url:GET|/api/v1/courses/:course_id/assignments",
    "url:GET|/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id",
    "url:GET|/api/v1/calendar_events",
    "url:GET|/api/v1/planner/items",
    "url:GET|/api/v1/courses/:course_id/modules",
    "url:GET|/api/v1/courses/:course_id/modules/:module_id/items",
    "url:GET|/api/v1/courses/:course_id/pages",
    "url:GET|/api/v1/courses/:course_id/files",
    "url:GET|/api/v1/files/:id",
    "url:GET|/api/v1/files/:id/public_url",
    "url:GET|/api/v1/announcements",
]


def friendly_errors(function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except CanvasError as error:
            typer.echo(f"Error [{error.code}]: {error.message}", err=True)
            raise typer.Exit(1) from None
        except ConfigError as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from None
        except (KeyboardInterrupt, EOFError):
            typer.echo("Cancelled.", err=True)
            raise typer.Exit(130) from None
        except Exception:
            # Never print exception bodies: upstream HTTP errors may carry tokens.
            typer.echo(
                (
                    "Error: The operation could not complete. Check connectivity and run "
                    "folava-mcp doctor. No credential details were printed."
                ),
                err=True,
            )
            raise typer.Exit(1) from None

    return wrapped


@auth_app.command("login")
@friendly_errors
def login(
    url: Annotated[str, typer.Option("--url", help="Canvas HTTPS origin.")],
    personal_token: Annotated[
        bool,
        typer.Option(
            "--personal-token", help="Use a personal token for the account owner's local testing."
        ),
    ] = False,
    profile: ProfileOption = "default",
) -> None:
    """Store a personal testing token using a masked prompt and the OS keyring."""
    if not personal_token:
        raise auth.AuthError(
            "For normal use, run folava-mcp auth oauth --url YOUR_CANVAS "
            "--client-id YOUR_ID. Personal local testing requires "
            "--personal-token."
        )
    auth.secure_keyring()
    typer.echo(
        "Personal tokens are for your own local testing. Public and "
        "multi-user applications require Canvas OAuth."
    )
    token = typer.prompt("Canvas personal token", hide_input=True, confirmation_prompt=False)
    metadata = auth.login_token(url, token, profile)
    typer.echo(
        f"Connected profile '{profile}' to {metadata.origin}. Credential stored in the OS keyring."
    )


@auth_app.command("oauth")
@friendly_errors
def oauth(
    url: Annotated[str, typer.Option("--url", help="Canvas HTTPS origin.")],
    client_id: Annotated[
        str, typer.Option("--client-id", help="Institution-approved Canvas developer key ID.")
    ],
    profile: ProfileOption = "default",
    redirect_uri: Annotated[
        str, typer.Option("--redirect-uri", help="Exact registered loopback callback URI.")
    ] = "http://127.0.0.1:8765/callback",
    scope: Annotated[
        list[str] | None,
        typer.Option(
            "--scope",
            help=(
                "Repeat to replace default scopes with explicit Canvas GET scopes. "
                "Profile scope is always included."
            ),
        ),
    ] = None,
    no_browser: Annotated[
        bool,
        typer.Option("--no-browser", help="Print the authorization URL without opening a browser."),
    ] = False,
) -> None:
    """Sign in through Canvas; an institution-approved developer key is required."""
    auth.secure_keyring()
    auth.validate_redirect_uri(redirect_uri)
    scopes = list(scope or DEFAULT_SCOPES)
    if DEFAULT_SCOPES[0] not in scopes:
        scopes.insert(0, DEFAULT_SCOPES[0])
    typer.echo("Use an institution-approved developer key with this exact redirect URI:")
    typer.echo(redirect_uri)
    typer.echo(
        "The default scopes cover common student reads; additional catalog "
        "endpoints require matching GET scopes on the key and token."
    )
    client_secret = typer.prompt("Developer key client secret", hide_input=True)
    metadata = auth.login_oauth(
        url,
        client_id,
        client_secret,
        scopes,
        profile=profile,
        redirect_uri=redirect_uri,
        open_browser=not no_browser,
        on_url=lambda value: typer.echo(f"Open this sign-in URL on this computer:\n{value}"),
    )
    typer.echo(
        f"Connected profile '{profile}' to {metadata.origin}. "
        "Access and refresh credentials stored in the OS keyring."
    )


@auth_app.command("logout")
@friendly_errors
def logout(
    profile: ProfileOption = "default",
    revoke: Annotated[
        bool,
        typer.Option(
            "--revoke",
            help=(
                "Also revoke this credential at Canvas. Other applications sharing it lose access."
            ),
        ),
    ] = False,
) -> None:
    """Remove a stored credential, optionally revoking it at Canvas first."""
    auth.logout(profile, revoke=revoke)
    typer.echo(
        "Canvas credential revoked and local profile removed."
        if revoke
        else "Local credential and profile removed. Canvas access was not revoked."
    )


@auth_app.command("status")
@friendly_errors
def status() -> None:
    """List configured profile metadata without reading secrets or refreshing tokens."""
    profiles = list_profiles()
    if not profiles:
        typer.echo("No stored profiles. Run folava-mcp auth oauth --help to connect Canvas.")
    for name, metadata in profiles.items():
        typer.echo(f"{name}\t{metadata.origin}\t{metadata.auth_kind}")


@app.command("config")
@friendly_errors
def client_config(
    profile: ProfileOption = "default",
    format: Annotated[str, typer.Option("--format", help="codex or json.")] = "codex",
    demo: Annotated[
        bool, typer.Option("--demo", help="Generate configuration for the offline demo.")
    ] = False,
) -> None:
    """Print credential-free client configuration; never modify existing files."""
    validate_profile_name(profile)
    args = ["serve", "--profile", profile] + (["--demo"] if demo else [])
    if format == "json":
        typer.echo(
            json.dumps(
                {"mcpServers": {"folava": {"command": "folava-mcp", "args": args}}}, indent=2
            )
        )
    elif format == "codex":
        typer.echo('[mcp_servers.folava]\ncommand = "folava-mcp"\nargs = ' + json.dumps(args))
    else:
        raise ConfigError("Choose --format codex or --format json.")


async def _doctor(profile: str) -> Any:
    from .client import CanvasClient

    credentials = auth.load_credentials(profile)
    async with CanvasClient(credentials.origin, credentials.token) as client:
        return await client.read("profile")


@app.command("doctor")
@friendly_errors
def doctor(profile: ProfileOption = "default") -> None:
    """Check local credentials and verify read-only Canvas profile access."""
    asyncio.run(_doctor(profile))
    typer.echo(
        f"Canvas profile '{profile}' is reachable. "
        "Authentication and read-only profile access work."
    )


async def _fetch_file(profile: str, file_id: str, max_bytes: int) -> dict[str, Any]:
    from .client import CanvasClient

    credentials = auth.load_credentials(profile)
    async with CanvasClient(credentials.origin, credentials.token) as client:
        return await client.file(file_id, max_bytes=max_bytes)


@app.command("file")
@friendly_errors
def export_file(
    file_id: Annotated[
        str, typer.Argument(help="Canvas file ID, from an assignment or file listing.")
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o", help="Create this file; existing files are never overwritten."
        ),
    ],
    profile: ProfileOption = "default",
    max_bytes: Annotated[int, typer.Option("--max-bytes", min=1, max=20_000_000)] = 5_000_000,
) -> None:
    """Save a Canvas attachment to an explicitly chosen private local file."""
    if output.exists() or output.is_symlink():
        raise ConfigError("Output already exists. Choose a new path; no file was changed.")
    result = asyncio.run(_fetch_file(profile, file_id, max_bytes))
    try:
        if "content_base64" in result:
            content = base64.b64decode(result["content_base64"], validate=True)
        elif isinstance(result.get("text"), str):
            content = result["text"].encode("utf-8")
        else:
            raise ValueError
        digest = hashlib.sha256(content).hexdigest()
        if len(content) > max_bytes or result.get("sha256") != digest:
            raise ValueError
    except (ValueError, TypeError):
        raise ConfigError(
            "Attachment content could not be verified. No file was created."
        ) from None
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ConfigError(
            "Output already exists. Choose a new path; no file was changed."
        ) from None
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
    except OSError:
        output.unlink(missing_ok=True)
        raise ConfigError("Attachment could not be saved. Check the output directory.") from None
    typer.echo(f"Saved {len(content)} bytes. SHA-256: {digest}")


@app.command("serve")
@friendly_errors
def serve(
    profile: ProfileOption = "default",
    demo: Annotated[
        bool,
        typer.Option(
            "--demo", help="Use bundled fictional data without credentials or network requests."
        ),
    ] = False,
) -> None:
    """Serve MCP over stdio. stdout is reserved exclusively for the protocol."""
    from .server import run

    run(profile=profile, demo=demo)


async def _poll(
    profile: str,
    state: Path,
    operation: str,
    path: dict[str, str] | None,
    query: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    from .client import CanvasClient
    from .events import poll_once

    credentials = auth.load_credentials(profile)
    async with CanvasClient(credentials.origin, credentials.token) as client:
        return await poll_once(client, state, operation, path=path, query=query)


@app.command("poll")
@friendly_errors
def poll(
    operation: Annotated[str, typer.Argument(help="Catalog list operation to monitor.")],
    profile: ProfileOption = "default",
    state: Annotated[
        Path | None,
        typer.Option("--state", help="Private durable state file; use one file per query."),
    ] = None,
    path: Annotated[
        str, typer.Option("--path", help="JSON object of endpoint path arguments.")
    ] = "{}",
    query: Annotated[
        str, typer.Option("--query", help="JSON object of allowed query parameters.")
    ] = "{}",
) -> None:
    """Poll once and print new durable events as JSON Lines; schedule externally."""
    try:
        path_value, query_value = json.loads(path), json.loads(query)
        if not isinstance(path_value, dict) or not isinstance(query_value, dict):
            raise ValueError
    except (ValueError, TypeError):
        raise ConfigError("--path and --query must be JSON objects.") from None
    validate_profile_name(profile)
    from .catalog import OPERATIONS

    if operation not in OPERATIONS:
        raise ConfigError("Unknown operation; choose a reviewed catalog operation.")
    destination = state or config_dir() / "events" / f"{profile}-{operation}.sqlite"
    for event in asyncio.run(_poll(profile, destination, operation, path_value, query_value)):
        typer.echo(json.dumps(event, ensure_ascii=False))


@events_app.command("read")
@friendly_errors
def events_read(
    state: Annotated[Path, typer.Option("--state", help="State file used by poll.")],
    after: Annotated[
        int, typer.Option("--after", min=0, help="Replay events after this sequence number.")
    ] = 0,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 100,
) -> None:
    """Replay recorded events without contacting Canvas."""
    from .events import read_events

    for event in read_events(state, after=after, limit=limit):
        typer.echo(json.dumps(event, ensure_ascii=False))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
