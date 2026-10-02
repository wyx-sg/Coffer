"""coffer channel ... commands (spec channels).

``list``, ``edit``, ``rm``, ``enable``, ``disable`` and ``scope`` are the
lifecycle verbs every kind's group shares (``_kind_verbs``); ``edit`` carries
the two group-gating switches as this kind's own flags. ``add`` and ``show``
are this kind's own: ``add`` takes a channel type's settings as flags and binds
the channel to this machine, and ``show`` reports the channel's status beside
its configuration. ``pair``, ``unpair``, ``bind``, ``restart`` and ``notify`` are channel-specific.
"""

from __future__ import annotations

import dataclasses
import json as _json
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._approvals import WAIT_OPTION, pending_for, settle
from coffer.surfaces.cli._channel_machine import (
    handover_warning,
    known_machines,
    this_machine_id,
)
from coffer.surfaces.cli._channel_options import (
    _DEFAULT_DIR,
    _DIRS,
    _IGNORE_OTHER_MENTIONS,
    _NEW_CONVERSATION_AFTER_IDLE,
    _NO_DEFAULT_DIR,
    _NO_DIRS,
    _NOTIFY_AFTER,
    _REQUIRE_MENTION,
    _SHOW_STEPS,
    _WAIT_AFTER_FORWARD,
    _WAIT_AFTER_TEXT,
    _settings,
    directories,
    edit_option,
    settings_config,
    with_default_dir,
)
from coffer.surfaces.cli._channel_people import pair, unpair
from coffer.surfaces.cli._channel_show import agent_name, echo_channel
from coffer.surfaces.cli._kind_verbs import (
    Column,
    EditFlags,
    KindVerbs,
    check_title_arg,
    register_kind_verbs,
    verbose_of,
)
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli._resolve import resolve_ref, resolve_uid

app = typer.Typer(help="Manage messaging channels (Telegram, SeaTalk)")


def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
    channel_type: str = typer.Option(..., "--type", help="telegram | seatalk"),
    bot_token_ref: str | None = typer.Option(
        None,
        "--bot-token-ref",
        help="Secret ref of the Telegram bot token (store it with `coffer secret set`)",
    ),
    app_id: str | None = typer.Option(None, "--app-id", help="SeaTalk App ID"),
    app_secret_ref: str | None = typer.Option(
        None,
        "--app-secret-ref",
        help="Secret ref of the SeaTalk app secret (store it with `coffer secret set`)",
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
    wait_after_text: float | None = _WAIT_AFTER_TEXT,
    wait_after_forward: float | None = _WAIT_AFTER_FORWARD,
    show_steps: bool | None = _SHOW_STEPS,
    notify_after: float | None = _NOTIFY_AFTER,
    new_conversation_after_idle_hours: float | None = _NEW_CONVERSATION_AFTER_IDLE,
    dirs: list[str] | None = _DIRS,
    default_dir: str | None = _DEFAULT_DIR,
    title: str | None = typer.Option(None, "--title", help="Display title (≤80 chars)"),
    description: str | None = typer.Option(None, "--description"),
    wait: bool = WAIT_OPTION,
) -> None:
    """Register a channel.

    Its secrets are secret refs: store each secret first with
    `coffer secret set`, then pass the ref here.

    \f
    The channel is bound to THIS machine unless ``--runs-on`` names another:
    a channel runs on exactly one machine, and the one the user is typing at is
    the only defensible guess. Binding at creation is also what keeps "unbound"
    rare enough to be an error state rather than a routine one.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    # The channel stores the agent's UID, so a rename cannot silently unbind it
    # — but a person types a NAME, so it is resolved here, once. It is required
    # rather than defaulted because a uid is minted per vault: no constant can
    # stand for "the usual agent".
    config: dict[str, Any] = {"channel_type": channel_type}
    config.update(
        _settings(
            require_mention,
            ignore_other_mentions,
            wait_after_text,
            wait_after_forward,
            show_steps,
            notify_after,
            new_conversation_after_idle_hours,
        )
    )
    allowed = directories(dirs, False)
    if allowed:
        config["directories"] = allowed
    if agent_config is not None:
        try:
            config["default_agent_config"] = _json.loads(agent_config)
        except _json.JSONDecodeError:
            typer.echo("--agent-config must be valid JSON", err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT)) from None
    started_in = with_default_dir(config.get("default_agent_config"), default_dir, False)
    if started_in is not None:
        config["default_agent_config"] = started_in
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
    check_title_arg(title)
    c, _info = _cli_client.client_or_exit()
    with c:
        config["runs_on"] = runs_on if runs_on else this_machine_id(c, verbose=verbose)
        # A new channel is created unscoped, so an enabled one starts here and
        # may drive every registered agent (ADR per-agent-resource-scope).
        # Narrowing the agents it may drive is a later, separate edit —
        # ``coffer channel scope <name> --agents <names>`` — not something
        # add has to ask about.
        config["default_agent"] = resolve_uid(c, "agent", default_agent, verbose=verbose)
        body = {"kind": "channel", "name": name, "config": config, "description": description}
        r = c.post("/resources", json=body)
        _cli_client.check(r, verbose=verbose)
        uid = r.json()["uid"]
        if title:
            r = c.patch(f"/resources/{uid}", json={"title": title})
            _cli_client.check(r, verbose=verbose)
        typer.echo(f"added: channel {name}")
        settle(c, pending_for(c, uid, verbose=verbose), wait=wait, verbose=verbose)


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
        known = [] if output_json else known_machines(c, verbose=verbose)
        agent_uid = (resource.get("config") or {}).get("default_agent") or ""
        agent = "-" if output_json or not agent_uid else agent_name(c, agent_uid, verbose=verbose)
    if output_json:
        typer.echo(_json.dumps({**resource, "status": body}, indent=2))
        return
    echo_channel(resource, body, agent=agent, known=known)


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
        here = this_machine_id(c, verbose=verbose)
        target = machine_id or here
        known = known_machines(c, verbose=verbose)
        if known and target not in known:
            # A mistyped id would bind the channel to nobody: it would run nowhere.
            typer.echo(f"no machine in this vault has the id {target}", err=True)
            raise typer.Exit(1)
        warning = handover_warning(config.get("runs_on"), target, here=here)
        config["runs_on"] = target
        r = c.patch(f"/resources/{uid}", json={"config": config})
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"channel {name} runs on {target}")
    if warning:
        typer.echo(warning)


def restart(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
) -> None:
    """Stop the channel's adapter and start it again, reading its secret afresh.

    Use it when a channel is stuck connecting, or to take a SeaTalk connection
    back from another process. Replacing a secret with `coffer secret set`
    already restarts the adapter on its own.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "channel", name, verbose=verbose)
        r = c.post(f"/channels/{uid}/restart")
        _cli_client.check(r, verbose=verbose)
    typer.echo(
        f"channel {name} restarted" if r.json().get("running") else f"channel {name} is not running"
    )


def notify(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
    text: str = typer.Argument(..., help="Message text"),
    chat: str | None = typer.Option(
        None, "--chat", help="Paired chat id to push to (default: the first paired person's DM)"
    ),
) -> None:
    """Push a message to one of the channel's paired chats.

    Without ``--chat`` it goes to the channel's first paired person's DM — its
    earliest pairing. Naming a chat the channel is not paired
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
            edit_option("require_mention", _REQUIRE_MENTION),
            edit_option("ignore_other_mentions", _IGNORE_OTHER_MENTIONS),
            edit_option("wait_after_text", _WAIT_AFTER_TEXT, float | None),
            edit_option("wait_after_forward", _WAIT_AFTER_FORWARD, float | None),
            edit_option("show_steps", _SHOW_STEPS),
            edit_option("notify_after", _NOTIFY_AFTER, float | None),
            edit_option(
                "new_conversation_after_idle_hours", _NEW_CONVERSATION_AFTER_IDLE, float | None
            ),
            edit_option("dirs", _DIRS, list[str] | None),
            edit_option("no_dirs", _NO_DIRS, bool),
            edit_option("default_dir", _DEFAULT_DIR, str | None),
            edit_option("no_default_dir", _NO_DEFAULT_DIR, bool),
        ),
        to_config=settings_config,
    ),
    help={
        "list": "List registered channels.",
        "edit": (
            "Change a channel's name, title, description, group gating, quiet windows, "
            "live status, completion ping, idle rollover, default directory or `/dir` "
            "directories."
        ),
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
app.command("unpair")(unpair)
app.command("bind")(bind)
app.command("restart")(restart)
app.command("notify")(notify)
