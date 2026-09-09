"""coffer channel ... commands (spec 009)."""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="Manage messaging channels (Telegram, SeaTalk)")
_console = Console()


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List registered channels."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/resources", params={"kind": "channel"})
        _cli_client.check(r, verbose=verbose)
    items = r.json()["resources"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    table = Table(title="Channels")
    for col in ("Name", "Type", "Agent", "Enabled"):
        table.add_column(col)
    for it in items:
        config = it.get("config", {})
        table.add_row(
            it["name"],
            str(config.get("channel_type", "")),
            str(config.get("default_agent", "")),
            "yes" if it.get("enabled") else "no",
        )
    _console.print(table)


@app.command("register")
def register(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
    channel_type: str = typer.Option(..., "--type", help="telegram | seatalk"),
    bot_token_ref: str | None = typer.Option(
        None, "--bot-token-ref", help="Keychain ref of the Telegram bot token"
    ),
    app_id: str | None = typer.Option(None, "--app-id", help="SeaTalk App ID"),
    app_secret_ref: str | None = typer.Option(
        None, "--app-secret-ref", help="Keychain ref of the SeaTalk app secret"
    ),
    signing_secret_ref: str | None = typer.Option(
        None, "--signing-secret-ref", help="Keychain ref of the SeaTalk signing secret"
    ),
    default_agent: str = typer.Option("claude_code", "--agent", help="Default agent key"),
    agent_config: str | None = typer.Option(
        None, "--agent-config", help="Default agent config as JSON"
    ),
    runs_on: str | None = typer.Option(
        None,
        "--runs-on",
        help="machine_id whose runtime starts this channel (default: this machine)",
    ),
) -> None:
    """Register a channel (secrets must already be in the keychain)."""
    verbose = (ctx.obj or {}).get("verbose", False)
    config: dict[str, Any] = {"channel_type": channel_type, "default_agent": default_agent}
    if agent_config is not None:
        try:
            config["default_agent_config"] = _json.loads(agent_config)
        except _json.JSONDecodeError:
            typer.echo("--agent-config must be valid JSON", err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT)) from None
    if channel_type == "telegram":
        if bot_token_ref is None:
            typer.echo("--bot-token-ref is required for telegram channels", err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT))
        config["bot_token_ref"] = bot_token_ref
    elif channel_type == "seatalk":
        missing = [
            flag
            for flag, value in (
                ("--app-id", app_id),
                ("--app-secret-ref", app_secret_ref),
                ("--signing-secret-ref", signing_secret_ref),
            )
            if value is None
        ]
        if missing:
            typer.echo(f"missing for seatalk channels: {', '.join(missing)}", err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT))
        config["app_id"] = app_id
        config["app_secret_ref"] = app_secret_ref
        config["signing_secret_ref"] = signing_secret_ref
    else:
        typer.echo("--type must be telegram or seatalk", err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT))
    c, _info = _cli_client.client_or_exit()
    with c:
        # Affinity (ADR-045 framework scope, amending spec 010 / ADR-043): the
        # creating surface binds the creating machine so the adapter actually
        # starts; an unbound channel runs nowhere. Bound via the resource's
        # `scope` (not `config["runs_on"]`, which is deprecated/inert — see
        # coffer.domain.channel.config) so it takes effect at runtime.
        bound = runs_on
        if bound is None:
            # Best-effort: bind the creating machine so the adapter starts.
            machines = c.get("/sync/machines")
            if machines.status_code == 200:
                bound = next(
                    (m["machine_id"] for m in machines.json()["machines"] if m["is_local"]),
                    None,
                )
        r = c.post("/resources", json={"kind": "channel", "name": name, "config": config})
        _cli_client.check(r, verbose=verbose)
        if bound is not None:
            scope_r = c.put(f"/resources/channel/{name}/scope", json={"scope": {bound: "*"}})
            _cli_client.check(scope_r, verbose=verbose)
        else:
            typer.echo(
                "note: no machine identity available — channel left unbound "
                "(it runs nowhere until you set --runs-on or bind it in the UI)",
                err=True,
            )
    typer.echo(f"registered: channel:{name}")


@app.command("pair")
def pair(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
) -> None:
    """Issue a pairing code; send it to the bot from your own account."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/channels/{name}/pairing-code")
        _cli_client.check(r, verbose=verbose)
    body = r.json()
    typer.echo(f"pairing code: {body['code']}")
    typer.echo(f"expires at:   {body['expires_at']}")
    typer.echo("Send this code to the bot from the account that should own the channel.")


@app.command("status")
def status(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Show runtime, pairing, and callback status."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/channels/{name}/status")
        _cli_client.check(r, verbose=verbose)
    body = r.json()
    if output_json:
        typer.echo(_json.dumps(body, indent=2))
        return
    typer.echo(f"channel:  {body['name']} ({body['channel_type']})")
    typer.echo(f"enabled:  {body['enabled']}    running: {body['running']}")
    typer.echo(f"pairing:  {'code pending' if body['pending_pairing'] else 'no pending code'}")
    peer = body.get("peer")
    if peer:
        typer.echo(f"peer:     {peer['display_name']} (chat {peer['chat_id']})")
        typer.echo(f"conv:     {peer.get('active_conversation_id') or '-'}")
    else:
        typer.echo("peer:     not paired")
    callback = body.get("callback")
    if callback:
        typer.echo(
            f"callback: 127.0.0.1:{callback['port']}{callback['path']} "
            f"(listener {'up' if callback['listener_running'] else 'down'})"
        )
        if callback.get("public_callback_url"):
            typer.echo(f"register: {callback['public_callback_url']}")


@app.command("notify")
def notify(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
    text: str = typer.Argument(..., help="Message text"),
) -> None:
    """Push a message to the channel's paired owner."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/channels/{name}/notify", json={"text": text})
        _cli_client.check(r, verbose=verbose)
    typer.echo("sent")
