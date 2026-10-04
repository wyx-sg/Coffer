"""``coffer memory hook`` and ``coffer memory delivered`` — memory's two
delivery moments after a session starts, from the terminal.

``hook`` is what each of Coffer's two installed entries runs. Its caller is an
agent's hook runner, not a person, so it must be fast and must never fail a
session: it reads the agent's hook JSON from stdin, answers locally whatever
needs no daemon (a trivial prompt), and otherwise asks the daemon with a short
timeout. Any failure at all — no daemon, a slow answer, a malformed one —
prints nothing and exits 0, so memory never stops a prompt because Coffer is
down. ``delivered`` prints the Memory page's two delivery views.
"""

from __future__ import annotations

import json as _json
import os
import sys

import httpx
import typer

from coffer.domain.channel_turn import is_channel_turn
from coffer.domain.memory import retrieval as ranking
from coffer.domain.memory.delivery import (
    CHANNEL_TURN_EVENTS,
    SESSION_START,
    USER_PROMPT_SUBMIT,
)
from coffer.infrastructure.daemon.bootstrap import live_daemon

#: Session start may take a little longer: it composes the whole index.
_SESSION_TIMEOUT_S = 3.0
#: A prompt waits at most this long, under the entry's own timeout.
_TURN_TIMEOUT_S = 2.0


def _needs_daemon(event: str, prompt: str) -> bool:
    """Whether this fire can deliver anything at all — answered locally, so an
    trivial prompt costs no round-trip.

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
    return False


def hook(
    agent_uid: str = typer.Option(
        ..., "--agent-uid", help="The uid of the agent whose hook is firing"
    ),
    cwd: str = typer.Option("", "--cwd", help="Fallback working directory"),
) -> None:
    """Answer one fire of Coffer's memory hook; reads the agent's hook JSON on stdin.

    Both installed memory hook entries run this; you rarely need to. It prints
    nothing, and exits 0, when the daemon is not running.
    """
    try:
        raw = "" if sys.stdin.isatty() else sys.stdin.read()
        ev = _json.loads(raw) if raw.strip() else {}
        if not isinstance(ev, dict):
            return
        event = str(ev.get("hook_event_name") or "")
        payload = {
            "agent_uid": agent_uid,
            "event": event,
            "session_id": str(ev.get("session_id") or ""),
            "cwd": str(ev.get("cwd") or cwd),
            "prompt": str(ev.get("prompt") or ""),
        }
        if not _needs_daemon(event, payload["prompt"]):
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


__all__ = ["hook"]
