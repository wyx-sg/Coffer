"""``coffer memory hook``, ``coffer memory trigger …`` and ``coffer memory
delivered`` — the three moments memory reaches a session after its start, from
the terminal (ADR memory-reaches-a-session-at-prompt-time-and-before-a-known-trap).

``hook`` is what every one of Coffer's four installed entries runs. Its caller
is an agent's hook runner, not a person, so like ``context`` it must be fast and
must never fail a session: it reads the agent's hook JSON from stdin, answers
locally whatever needs no daemon (a trivial prompt, a command no armed trigger
matches), and otherwise asks the daemon with a short timeout. Any failure at
all — no daemon, a slow answer, a malformed one — prints nothing and exits 0,
so memory never stops a prompt or a command because Coffer is down.

``trigger`` lists, writes, arms, disarms and deletes the authored guards in
``vault/memory-triggers/`` (spec memory "Keep triggers in the vault, armed only
by a person"). ``delivered`` prints the Memory page's two delivery views.
"""

from __future__ import annotations

import json as _json
import os
import sys
from typing import Any

import httpx
import typer

from coffer.domain.channel_turn import is_channel_turn
from coffer.domain.memory import retrieval as ranking
from coffer.domain.memory.delivery import (
    CHANNEL_TURN_EVENTS,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    SESSION_START,
    SHELL_TOOL_MATCHER,
    USER_PROMPT_SUBMIT,
)
from coffer.domain.memory.trigger import KIND_BLOCK, KIND_CONTEXT, matches_command, matches_error
from coffer.infrastructure.daemon.bootstrap import live_daemon
from coffer.infrastructure.memory import trigger_store
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

#: Session start may take a little longer: it composes the whole index.
_SESSION_TIMEOUT_S = 3.0
#: A prompt or a command waits at most this long, under the entry's own timeout.
_TURN_TIMEOUT_S = 2.0
#: The tail of a command's output that is sent for error matching.
_MAX_OUTPUT_CHARS = 20_000

trigger_app = typer.Typer(help="List, write, arm, disarm and delete memory triggers")


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def _output_text(response: Any) -> str:
    """A tool's response as text: Claude Code hands an object of streams,
    Codex a string."""
    if isinstance(response, str):
        text = response
    elif isinstance(response, dict):
        parts = [str(v) for k, v in response.items() if isinstance(v, str) and k != "type"]
        text = "\n".join(parts)
    elif response is None:
        text = ""
    else:
        text = _json.dumps(response, ensure_ascii=False)
    return text[-_MAX_OUTPUT_CHARS:]


def _needs_daemon(event: str, prompt: str, tool: str, command: str, output: str) -> bool:
    """Whether this fire can deliver anything at all — answered locally, so an
    ordinary command costs no round-trip.

    In a process Coffer spawned for a channel turn, the index and the prompt's
    notes are already in the turn Coffer composed (spec memory "Deliver to
    channel turns through the system prompt"), so those two moments are left to
    it: answering them here too would hand the agent the same text twice and
    audit it twice."""
    if event in CHANNEL_TURN_EVENTS and is_channel_turn(os.environ):
        return False
    if event == SESSION_START:
        return True
    if event == USER_PROMPT_SUBMIT:
        return ranking.is_substantive(prompt)
    if tool != SHELL_TOOL_MATCHER or event not in (PRE_TOOL_USE, POST_TOOL_USE):
        return False
    armed = [t for t in trigger_store.list_triggers() if t.armed]
    if event == PRE_TOOL_USE:
        return any(t.kind == KIND_BLOCK and matches_command(t, command) for t in armed)
    return any(t.kind == KIND_CONTEXT and matches_error(t, command, output) for t in armed)


def hook(
    agent_uid: str = typer.Option(
        ..., "--agent-uid", help="The uid of the agent whose hook is firing"
    ),
    cwd: str = typer.Option("", "--cwd", help="Fallback working directory"),
) -> None:
    """Answer one fire of Coffer's memory hook; reads the agent's hook JSON on stdin.

    Every installed memory hook entry runs this; you rarely need to. It prints
    nothing, and exits 0, when the daemon is not running.
    """
    try:
        raw = "" if sys.stdin.isatty() else sys.stdin.read()
        ev = _json.loads(raw) if raw.strip() else {}
        if not isinstance(ev, dict):
            return
        event = str(ev.get("hook_event_name") or "")
        raw_input = ev.get("tool_input")
        tool_input: dict[str, Any] = raw_input if isinstance(raw_input, dict) else {}
        payload = {
            "agent_uid": agent_uid,
            "event": event,
            "session_id": str(ev.get("session_id") or ""),
            "cwd": str(ev.get("cwd") or cwd),
            "prompt": str(ev.get("prompt") or ""),
            "tool_name": str(ev.get("tool_name") or ""),
            "command": str(tool_input.get("command") or ""),
            "output": _output_text(ev.get("tool_response")),
        }
        if not _needs_daemon(
            event, payload["prompt"], payload["tool_name"], payload["command"], payload["output"]
        ):
            return
        info = live_daemon()
        if info is None:
            return
        resp = httpx.post(
            f"http://127.0.0.1:{info.port}/api/v1/memory/hook",
            json=payload,
            headers={"X-Coffer-Token": info.token, "X-Coffer-Actor": "cli"},
            timeout=_SESSION_TIMEOUT_S if event == SESSION_START else _TURN_TIMEOUT_S,
        )
        if resp.status_code != 200:
            return
        output = resp.json().get("output")
        if output:
            typer.echo(_json.dumps(output, ensure_ascii=False))
    except Exception:
        return


# --------------------------------------------------------------------------- #
# coffer memory trigger …                                                      #
# --------------------------------------------------------------------------- #


def _print_trigger(t: dict[str, Any]) -> None:
    state = "armed" if t["armed"] else "proposed"
    pattern = t["command"] or t["error"]
    typer.echo(f"{t['id']}  {state}  {t['kind']}  {t['note']}  {pattern}")


@trigger_app.command("list")
def trigger_list(
    ctx: typer.Context, output_json: bool = typer.Option(False, "--json", help="JSON output")
) -> None:
    """List every trigger, armed or proposed."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/memory/triggers")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    if not data["triggers"]:
        typer.echo("no memory triggers")
    for t in data["triggers"]:
        _print_trigger(t)


@trigger_app.command("add")
def trigger_add(
    ctx: typer.Context,
    note: str = typer.Option(..., "--note", help="<partition>/<slug> of the note"),
    kind: str = typer.Option(KIND_BLOCK, "--kind", help="block or context"),
    command: str = typer.Option("", "--command", help="Regex over the executing command"),
    unless: str = typer.Option("", "--unless", help="Regex that keeps the trigger quiet"),
    error: str = typer.Option("", "--error", help="Regex over the command's output"),
    body: str = typer.Option("", "--body", help="Reason to show when the note is gone"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Write a trigger; it is armed by you as it is written."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            "/memory/triggers",
            json={
                "note": note,
                "kind": kind,
                "command": command,
                "unless": unless,
                "error": error,
                "body": body,
            },
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    if output_json:
        typer.echo(_json.dumps(r.json(), indent=2))
    else:
        _print_trigger(r.json())


def _act(ctx: typer.Context, trigger_id: str, action: str) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/memory/triggers/{trigger_id}/{action}")
        _cli_client.check(r, verbose=_verbose(ctx))
    _print_trigger(r.json())


@trigger_app.command("arm")
def trigger_arm(ctx: typer.Context, trigger_id: str = typer.Argument(...)) -> None:
    """Arm a trigger — a proposal takes effect only once a person arms it."""
    _act(ctx, trigger_id, "arm")


@trigger_app.command("disarm")
def trigger_disarm(ctx: typer.Context, trigger_id: str = typer.Argument(...)) -> None:
    """Disarm a trigger; it stays, as a proposal."""
    _act(ctx, trigger_id, "disarm")


@trigger_app.command("delete")
def trigger_delete(ctx: typer.Context, trigger_id: str = typer.Argument(...)) -> None:
    """Delete a trigger's file."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/memory/triggers/{trigger_id}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted {trigger_id}")


# --------------------------------------------------------------------------- #
# coffer memory delivered                                                      #
# --------------------------------------------------------------------------- #


def delivered(
    ctx: typer.Context,
    partition: str = typer.Argument(
        None, help="A partition: print what each agent is given at session start"
    ),
    agent: str = typer.Option("", "--agent", help="Only this agent's text"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """What memory delivered in the last seven days, per agent — or, for one
    partition, the exact session-start text each agent is given."""
    c, _info = _cli_client.client_or_exit()
    with c:
        if partition is None:
            r = c.get("/memory/deliveries")
        else:
            uid = resolve_uid(c, "memory", partition, verbose=_verbose(ctx))
            r = c.get(f"/memory/partitions/{uid}/delivered")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if partition is not None and agent:
        data["agents"] = [a for a in data["agents"] if agent in (a["agent_name"], a["agent_uid"])]
    if output_json:
        typer.echo(_json.dumps(data, indent=2, ensure_ascii=False))
        return
    if partition is None:
        for a in data["agents"]:
            read = a["notes_read"] if a["notes_read"] is not None else "unavailable"
            last = a["last_delivered_at"] or "never"
            typer.echo(
                f"{a['agent_name']}: {a['deliveries']} deliveries in {data['window_days']} days, "
                f"notes read: {read}, last: {last}"
            )
        return
    for a in data["agents"]:
        typer.echo(f"== {a['agent_name']} ({a['event']}) ==")
        typer.echo(a["text"] or "(nothing to deliver)")


__all__ = ["delivered", "hook", "trigger_app"]
