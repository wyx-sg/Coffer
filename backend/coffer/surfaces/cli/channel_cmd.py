"""coffer channel ... commands (spec channels).

``list``, ``edit``, ``rm``, ``enable``, ``disable`` and ``scope`` are the
lifecycle verbs every kind's group shares (``_kind_verbs``); ``edit`` carries
the two group-gating switches as this kind's own flags. ``add`` and ``show``
are this kind's own: ``add`` takes a channel type's settings as flags and binds
the channel to this machine, and ``show`` reports the channel's status beside
its configuration. ``pair``, ``bind`` and ``notify`` are channel-specific.
"""

from __future__ import annotations

import dataclasses
import inspect
import json as _json
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import (
    Column,
    EditFlags,
    KindVerbs,
    label,
    register_kind_verbs,
    verbose_of,
)
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli._resolve import resolve_ref, resolve_uid

app = typer.Typer(help="Manage messaging channels (Telegram, SeaTalk)")


def _this_machine_id(client: Any, *, verbose: bool) -> str:
    """This daemon's machine id, from the surface that already publishes it.

    The CLI cannot derive it: the id is read from the host by the daemon and
    cached beside the database, and a CLI deriving its own would be a second
    answer to an identity question that must have exactly one. Read off the
    daemon's status rather than the sync surface: a channel is bound to a
    machine whether or not ``vault_sync`` is switched on.
    """
    r = client.get("/daemon/status")
    _cli_client.check(r, verbose=verbose)
    machine_id = _cli_client.status_machine_id(r.json())
    if not machine_id:
        typer.echo("the daemon has not derived this machine's id yet — try again", err=True)
        raise typer.Exit(1)
    return str(machine_id)


# Group gating (spec channels "Configure when the bot answers in a group"):
# tri-state, so an option left out keeps the stored value (or, at register,
# the config's own default) instead of overwriting it.
_REQUIRE_MENTION = typer.Option(
    None,
    "--require-mention/--no-require-mention",
    help="In groups, answer only when @mentioned or replied to (default: on)",
)
_IGNORE_OTHER_MENTIONS = typer.Option(
    None,
    "--ignore-other-mentions/--no-ignore-other-mentions",
    help="In groups, drop a message that @mentions anyone else (default: off)",
)


def _gating(require_mention: bool | None, ignore_other_mentions: bool | None) -> dict[str, bool]:
    """The group-gating config keys the user actually passed."""
    out: dict[str, bool] = {}
    if require_mention is not None:
        out["require_mention"] = require_mention
    if ignore_other_mentions is not None:
        out["ignore_other_mentions"] = ignore_other_mentions
    return out


def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
    channel_type: str = typer.Option(..., "--type", help="telegram | seatalk"),
    bot_token_ref: str | None = typer.Option(
        None,
        "--bot-token-ref",
        help="Credential ref of the Telegram bot token (store it with `coffer credentials set`)",
    ),
    app_id: str | None = typer.Option(None, "--app-id", help="SeaTalk App ID"),
    app_secret_ref: str | None = typer.Option(
        None,
        "--app-secret-ref",
        help="Credential ref of the SeaTalk app secret (store it with `coffer credentials set`)",
    ),
    default_agent: str = typer.Option(
        ...,
        "--agent",
        help="Name of the agent this channel drives by default (required)",
    ),
    agent_config: str | None = typer.Option(
        None, "--agent-config", help="Default agent config as JSON"
    ),
    runs_on: str | None = typer.Option(
        None,
        "--runs-on",
        help="machine_id of the machine that runs this channel (default: this one)",
    ),
    require_mention: bool | None = _REQUIRE_MENTION,
    ignore_other_mentions: bool | None = _IGNORE_OTHER_MENTIONS,
    title: str | None = typer.Option(None, "--title", help="Display title (≤80 chars)"),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Register a channel.

    Its secrets are credential refs: store each secret first with
    `coffer credentials set`, then pass the ref here.

    \f
    The channel is bound to THIS machine unless ``--runs-on`` names another:
    a channel runs on exactly one machine, and the one the user is typing at is
    the only defensible guess. Binding at creation is also what keeps "unbound"
    rare enough to be an error state rather than a routine one.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    # The channel stores the agent's UID, so a rename cannot silently unbind it
    # — but a person types a NAME, so it is resolved here, once, like every
    # other label this CLI takes. It is required rather than defaulted because
    # a uid is minted per vault: no constant can stand for "the usual agent",
    # and the old ``claude_code`` default was a fiction — there was never an
    # agent behind it, so a channel created with it simply routed nowhere.
    config: dict[str, Any] = {"channel_type": channel_type}
    config.update(_gating(require_mention, ignore_other_mentions))
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
        # spec channels/seatalk "Configure a SeaTalk channel by app id and
        # secret reference": the websocket register handshake authenticates
        # from these two alone, so they are the whole SeaTalk configuration.
        required = [("--app-id", app_id), ("--app-secret-ref", app_secret_ref)]
        missing = [flag for flag, value in required if value is None]
        if missing:
            typer.echo(f"missing for seatalk channels: {', '.join(missing)}", err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT))
        config["app_id"] = app_id
        config["app_secret_ref"] = app_secret_ref
    else:
        typer.echo("--type must be telegram or seatalk", err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT))
    c, _info = _cli_client.client_or_exit()
    with c:
        config["runs_on"] = runs_on if runs_on else _this_machine_id(c, verbose=verbose)
        # A new channel is created unscoped, so an enabled one starts here and
        # may drive every registered agent (ADR per-agent-resource-scope).
        # Narrowing the agents it may drive is a later, separate edit —
        # ``coffer channel scope <name> --agents <names>`` — not something
        # add has to ask about.
        config["default_agent"] = resolve_uid(c, "agent", default_agent, verbose=verbose)
        body = {"kind": "channel", "name": name, "config": config, "description": description}
        r = c.post("/resources", json=body)
        _cli_client.check(r, verbose=verbose)
        if title:
            r = c.patch(f"/resources/{r.json()['uid']}", json={"title": title})
            _cli_client.check(r, verbose=verbose)
    typer.echo(f"added: channel {name}")


def pair(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
) -> None:
    """Issue a pairing code; send it to the bot from your own account."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "channel", name, verbose=verbose)
        r = c.post(f"/channels/{uid}/pairing-code")
        _cli_client.check(r, verbose=verbose)
    body = r.json()
    typer.echo(f"pairing code: {body['code']}")
    typer.echo(f"expires at:   {body['expires_at']}")
    if body.get("pair_url"):
        # "Pair by a one-tap start link": opening the link pairs in one tap; the
        # code still works typed.
        typer.echo(f"pair link:    {body['pair_url']}")
    typer.echo("Send this code to the bot from the account that should own the channel.")


def show(
    ctx: typer.Context,
    ref: str = typer.Argument(..., metavar="NAME", help="Name or uid"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Show a channel's configuration and status (runtime, binding, pairing, inbound).

    \f
    Two reads: the resource document (``GET /resources/{uid}``) and the
    channel's status (``GET /channels/{uid}/status``); ``--json`` carries the
    document with the status under ``status`` (spec channels "Manage channels
    from the Channels page and the CLI").
    """
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        resource = resolve_ref(c, "channel", ref, verbose=verbose)
        r = c.get(f"/channels/{resource['uid']}/status")
        _cli_client.check(r, verbose=verbose)
    body = r.json()
    if output_json:
        typer.echo(_json.dumps({**resource, "status": body}, indent=2))
        return
    config = resource.get("config") or {}
    typer.echo(f"channel:  {label(resource)} ({body['channel_type']})")
    if resource.get("title"):
        typer.echo(f"name:     {resource['name']}")
    typer.echo(f"uid:      {resource['uid']}")
    if resource.get("description"):
        typer.echo(f"about:    {resource['description']}")
    typer.echo(f"agent:    {config.get('default_agent') or '-'}")
    typer.echo(
        f"gating:   require_mention={'on' if config.get('require_mention', True) else 'off'}"
        f"  ignore_other_mentions={'on' if config.get('ignore_other_mentions') else 'off'}"
    )
    for key in sorted(k for k in config if k.endswith("_ref")):
        typer.echo(f"secret:   {key} = {config[key]}")
    typer.echo(f"enabled:  {body['enabled']}    running: {body['running']}")
    # spec channels "Bind each channel to the one machine that runs it": unbound runs
    # nowhere and is said so — never dressed as the normal "another machine" state.
    binding = body.get("runs_on")
    if not binding:
        typer.echo("runs on:  unbound (runs nowhere)")
    else:
        where = "this machine" if body.get("runs_here") else "another machine"
        typer.echo(f"runs on:  {binding} ({where})")
    typer.echo(f"pairing:  {'code pending' if body['pending_pairing'] else 'no pending code'}")
    peer = body.get("peer")
    if peer:
        typer.echo(f"peer:     {peer['display_name']} (chat {peer['chat_id']})")
        typer.echo(f"conv:     {peer.get('active_conversation_id') or '-'}")
    else:
        typer.echo("peer:     not paired")
    inbound = body.get("inbound")
    if inbound:
        _echo_inbound(inbound)
    for diagnostic in body.get("diagnostics") or []:
        # spec channels/telegram "Report privacy mode that defeats the group
        # configuration": a setting that reads correctly here and does nothing in
        # the chat is worth interrupting for.
        typer.echo(f"warning:  {diagnostic['message']}")


def _echo_inbound(inbound: dict[str, object]) -> None:
    """The inbound lines of ``coffer channel show`` for a SeaTalk channel.

    Spec channels/seatalk "Report the websocket connection as the channel's
    inbound state": the connection state and its last error, and nothing about
    a listener, port, path, URL or tunnel — none exists.
    """
    state = inbound.get("websocket_state") or "not connected yet"
    typer.echo(f"inbound:  websocket ({state})")
    error = inbound.get("websocket_error")
    if error:
        # Verbatim: the two failures that matter (no SDK installed, another
        # process holding the connection) are only actionable if read.
        typer.echo(f"ws error: {error}")


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
        uid = resolve_uid(c, "channel", name, verbose=verbose)
        r = c.get(f"/resources/{uid}")
        _cli_client.check(r, verbose=verbose)
        config = dict(r.json().get("config") or {})
        config["runs_on"] = machine_id if machine_id else _this_machine_id(c, verbose=verbose)
        r = c.patch(f"/resources/{uid}", json={"config": config})
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"channel {name} runs on {config['runs_on']}")


def notify(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
    text: str = typer.Argument(..., help="Message text"),
    chat: str | None = typer.Option(
        None, "--chat", help="Paired chat id to push to (default: the owner's DM)"
    ),
) -> None:
    """Push a message to one of the channel's paired chats.

    Without ``--chat`` it goes to the owner chat — the channel's earliest
    pairing, which is the owner's DM. Naming a chat the channel is not paired
    to is refused rather than delivered somewhere else.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    body: dict[str, str] = {"text": text}
    if chat:
        body["chat_id"] = chat
    with c:
        uid = resolve_uid(c, "channel", name, verbose=verbose)
        r = c.post(f"/channels/{uid}/notify", json=body)
        _cli_client.check(r, verbose=verbose)
    typer.echo("sent")


def _gating_config(resource: dict[str, Any], values: dict[str, Any]) -> dict[str, Any] | None:
    """The stored config with only the switches given changed (``edit``)."""
    changes = _gating(values.get("require_mention"), values.get("ignore_other_mentions"))
    if not changes:
        return None
    return {**(resource.get("config") or {}), **changes}


def _option(name: str, default: Any) -> inspect.Parameter:
    return inspect.Parameter(
        name, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=default, annotation=bool | None
    )


_CHANNEL = KindVerbs(
    kind="channel",
    noun="channel",
    verbs=frozenset({"list", "edit", "rm", "enable", "disable", "scope"}),
    columns=(
        Column("Type", lambda it: str((it.get("config") or {}).get("channel_type", ""))),
        Column("Agent", lambda it: str((it.get("config") or {}).get("default_agent", ""))),
        # The machine id rather than a name: resolving a name needs the
        # machine registry, which only exists once this vault converges
        # with a remote. `coffer sync machine list` maps the two.
        Column("Runs on", lambda it: str((it.get("config") or {}).get("runs_on") or "unbound")),
    ),
    edit_flags=EditFlags(
        params=(
            _option("require_mention", _REQUIRE_MENTION),
            _option("ignore_other_mentions", _IGNORE_OTHER_MENTIONS),
        ),
        to_config=_gating_config,
    ),
    help={
        "list": "List registered channels.",
        "edit": "Change a channel's name, title, description or group-gating switches.",
        "rm": "Remove a channel and its pairings.",
        "enable": "Enable a channel (its adapter starts on the machine it is bound to).",
        "disable": "Disable a channel (its adapter stops).",
        "scope": "Show or set which agents a channel may drive (this machine only).",
    },
)


# Registered in one order so `--help` reads lifecycle first, then the
# channel-specific commands.
register_kind_verbs(app, dataclasses.replace(_CHANNEL, verbs=frozenset({"list"})))
app.command("show")(show)
app.command("add")(add)
register_kind_verbs(app, dataclasses.replace(_CHANNEL, verbs=_CHANNEL.verbs - {"list"}))
app.command("pair")(pair)
app.command("bind")(bind)
app.command("notify")(notify)
