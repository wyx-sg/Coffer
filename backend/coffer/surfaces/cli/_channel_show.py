"""The pieces of ``coffer channel show`` that read the daemon beyond the channel's
own status — split out of ``channel_cmd`` for its size budget."""

from __future__ import annotations

from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._channel_machine import binding_label
from coffer.surfaces.cli._kind_verbs import label

__all__ = ["agent_name", "echo_channel", "echo_inbound"]


def agent_name(client: Any, uid: str, *, verbose: bool) -> str:
    """The agent's name for ``uid`` — what a person recognises — falling back to
    the uid when the row is gone (a channel can outlive the agent it names)."""
    r = client.get(f"/resources/{uid}")
    if r.status_code == 404:
        return uid
    _cli_client.check(r, verbose=verbose)
    return str(r.json().get("name") or uid)


def echo_inbound(inbound: dict[str, object]) -> None:
    """The inbound lines of ``coffer channel show`` for a SeaTalk channel.

    Spec channels/seatalk "Report the websocket connection as the channel's
    inbound state": the connection state and its last error, and nothing about
    a listener, port, path, URL or tunnel — none exists.
    """
    state = inbound.get("websocket_state") or "not connected yet"
    typer.echo(f"inbound:  websocket ({state})")
    error = inbound.get("websocket_error")
    if error:  # verbatim: a missing SDK or a held connection is actionable only if read
        typer.echo(f"ws error: {error}")


def echo_channel(
    resource: dict[str, Any], body: dict[str, Any], *, agent: str, known: list[Any]
) -> None:
    """The plain-text report of ``coffer channel show``: the resource document
    beside the channel's status."""
    config = resource.get("config") or {}
    typer.echo(f"channel:  {label(resource)} ({body['channel_type']})")
    if resource.get("title"):
        typer.echo(f"name:     {resource['name']}")
    typer.echo(f"uid:      {resource['uid']}")
    if resource.get("description"):
        typer.echo(f"about:    {resource['description']}")
    typer.echo(f"agent:    {agent}")
    # The typed settings, defaults filled in by the daemon; ``None`` only when the
    # stored configuration no longer validates.
    settings = body.get("settings") or {}
    typer.echo(
        f"gating:   require_mention={'on' if settings.get('require_mention') else 'off'}"
        f"  ignore_other_mentions={'on' if settings.get('ignore_other_mentions') else 'off'}"
    )
    idle = settings.get("new_conversation_after_idle_hours")
    if idle is not None:
        typer.echo(f"idle:     {f'new conversation after {idle:g} h idle' if idle else 'never'}")
    default_dir = (config.get("default_agent_config") or {}).get("cwd")
    if default_dir:
        typer.echo(f"default:  {default_dir}")
    for path in config.get("directories") or []:
        typer.echo(f"dir:      {path}")
    for key in sorted(k for k in config if k.endswith("_ref")):
        typer.echo(f"secret:   {key} = {config[key]}")
    typer.echo(f"enabled:  {body['enabled']}    running: {body['running']}")
    # spec channels "Bind each channel to the one machine that runs it": unbound runs
    # nowhere and is said so — never dressed as the normal "another machine" state.
    binding = body.get("runs_on")
    if not binding:
        typer.echo("runs on:  unbound (runs nowhere)")
    else:
        here = bool(body.get("runs_here"))
        typer.echo(f"runs on:  {binding_label(binding, runs_here=here, known=known)}")
    typer.echo(f"pairing:  {'code pending' if body['pending_pairing'] else 'no pending code'}")
    people = body.get("people") or []
    if people:
        for person in people:
            typer.echo(
                f"person:   {person['display_name']} ({person['sender_id']}, "
                f"chat {person['chat_id']}, paired {person['paired_at']})"
            )
            typer.echo(f"conv:     {person.get('active_conversation_id') or '-'}")
    else:
        typer.echo("person:   nobody paired")
    inbound = body.get("inbound")
    if inbound:
        echo_inbound(inbound)
    for diagnostic in body.get("diagnostics") or []:
        # spec channels/telegram "Report privacy mode that defeats the group
        # configuration": a setting that reads correctly here and does nothing in
        # the chat is worth interrupting for.
        typer.echo(f"warning:  {diagnostic['message']}")
    if body.get("handoff"):
        # The same hand-off the channel page offers (the SDK is missing).
        typer.echo(f"\nFor your agent:\n{body['handoff']['prompt']}")
