"""coffer channel ... commands (spec channels)."""

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


def _this_machine_id(client: Any, *, verbose: bool) -> str:
    """This daemon's machine id, from the surface that already publishes it.

    The CLI cannot derive it: the id is read from the host by the daemon and
    cached beside the database, and a CLI deriving its own would be a second
    answer to an identity question that must have exactly one.
    """
    r = client.get("/sync/status")
    _cli_client.check(r, verbose=verbose)
    return str(r.json()["machine_id"])


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
    # "Runs on" is the machine id rather than a name: resolving a name needs
    # the machine registry, which only exists once this vault converges with a
    # remote, and a column that is blank on a single-machine install would say
    # less than the id does. `coffer sync machines` maps the two.
    for col in ("Name", "Type", "Agent", "Enabled", "Runs on"):
        table.add_column(col)
    for it in items:
        config = it.get("config", {})
        table.add_row(
            it["name"],
            str(config.get("channel_type", "")),
            str(config.get("default_agent", "")),
            "yes" if it.get("enabled") else "no",
            str(config.get("runs_on") or "unbound"),
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
    delivery: str = typer.Option(
        "webhook",
        "--delivery",
        help="SeaTalk event delivery: webhook (public callback URL) | websocket (no public URL)",
    ),
    default_agent: str = typer.Option("claude_code", "--agent", help="Default agent key"),
    agent_config: str | None = typer.Option(
        None, "--agent-config", help="Default agent config as JSON"
    ),
    runs_on: str | None = typer.Option(
        None,
        "--runs-on",
        help="machine_id of the machine that runs this channel (default: this one)",
    ),
) -> None:
    """Register a channel (secrets must already be in the keychain).

    The channel is bound to THIS machine unless ``--runs-on`` names another:
    a channel runs on exactly one machine, and the one the user is typing at is
    the only defensible guess. Binding at creation is also what keeps "unbound"
    rare enough to be an error state rather than a routine one.
    """
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
        if delivery not in {"webhook", "websocket"}:
            typer.echo("--delivery must be webhook or websocket", err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT))
        required = [("--app-id", app_id), ("--app-secret-ref", app_secret_ref)]
        if delivery == "webhook":
            # Only webhook delivery has anything signed to verify (FR-071).
            required.append(("--signing-secret-ref", signing_secret_ref))
        elif signing_secret_ref is not None:
            typer.echo(
                "--signing-secret-ref does not apply to websocket delivery "
                "(nothing is signed on that transport)",
                err=True,
            )
            raise typer.Exit(int(ExitCode.INVALID_INPUT))
        missing = [flag for flag, value in required if value is None]
        if missing:
            typer.echo(f"missing for seatalk channels: {', '.join(missing)}", err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT))
        config["app_id"] = app_id
        config["app_secret_ref"] = app_secret_ref
        config["delivery"] = delivery
        if delivery == "webhook":
            config["signing_secret_ref"] = signing_secret_ref
    else:
        typer.echo("--type must be telegram or seatalk", err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT))
    c, _info = _cli_client.client_or_exit()
    with c:
        config["runs_on"] = runs_on if runs_on else _this_machine_id(c, verbose=verbose)
        # A new channel is created unscoped, so an enabled one starts here and
        # may drive every registered agent (ADR per-agent-resource-scope).
        # Narrowing the agents it may drive is a later, separate edit —
        # ``coffer scope set channel:<name> --agents <keys>`` — not something
        # register has to ask about.
        r = c.post("/resources", json={"kind": "channel", "name": name, "config": config})
        _cli_client.check(r, verbose=verbose)
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
    if body.get("pair_url"):
        # FR-066: opening the link pairs in one tap; the code still works typed.
        typer.echo(f"pair link:    {body['pair_url']}")
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
    binding = body.get("runs_on") or "unbound"
    where = "this machine" if body.get("runs_here") else "another machine"
    typer.echo(f"runs on:  {binding} ({where})")
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
    for diagnostic in body.get("diagnostics") or []:
        # FR-060: a setting that reads correctly here and does nothing in the
        # chat is worth interrupting for.
        typer.echo(f"warning:  {diagnostic['message']}")


@app.command("bind")
def bind(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
    machine_id: str | None = typer.Argument(
        None, help="machine_id to bind to (default: this machine)"
    ),
) -> None:
    """Bind a channel to the machine that should run its adapter.

    Takes effect without a restart: the binding is config, and both daemons
    reconcile config on their own loop. The machine LOSING the channel stops
    its adapter within a tick of seeing the change; the machine gaining it
    starts one within a tick of the converge round that brings the change over.
    Run it from the machine that currently holds the channel and the handover
    has no overlap at all.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/resources/channel/{name}")
        _cli_client.check(r, verbose=verbose)
        config = dict(r.json().get("config") or {})
        config["runs_on"] = machine_id if machine_id else _this_machine_id(c, verbose=verbose)
        r = c.patch(f"/resources/channel/{name}", json={"config": config})
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"channel:{name} runs on {config['runs_on']}")


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
