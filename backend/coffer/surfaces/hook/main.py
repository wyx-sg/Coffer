"""``coffer-hook`` — the agent session-lifecycle → Coffer-daemon bridge.

Spawned by the agent (Claude Code / Codex / Cursor as a hook; opencode and
openclaw via Coffer's dropped plugins) at SessionStart / SessionEnd. Reads the hook JSON from
stdin and the Coffer agent name from ``--agent <name>`` (the hook payload does
not carry Coffer's agent identity), then talks to the local daemon discovered
via ``~/.coffer/daemon.json``:

- **SessionStart** → ``GET /api/v1/agents/{agent}/session-context?cwd=<cwd>``;
  on 200 print the rules bundle in the dialect's envelope so the agent injects it.
- **SessionEnd** → ``POST /api/v1/agents/{agent}/sessions/{session_id}/end``
  with ``{"cwd": cwd}``; the body is ignored.

``--dialect`` selects the stdout envelope (``claude`` — the default — prints
``hookSpecificOutput.additionalContext``; ``cursor`` prints a top-level
``additional_context``; ``raw`` prints the bundle text with no envelope — the
PLUGIN_DROP plugin file spawns this and pushes stdout onto the system prompt).
``--event`` names the event when the agent's stdin
payload does not: Cursor keys its hooks.json by event, so the event is baked into
the installed command's args instead. When ``--event`` names a SessionStart the
payload is never read at all — stdin has no timeout, and an agent that leaves it
open would otherwise stall on this hook.

``cwd`` scopes the rules/memory bundle. It comes from the payload, else from the
hook's own working directory (inherited from the agent). When neither is
available it is OMITTED — never sent empty, which the daemon would resolve
against its own long-lived working directory.

THE CONTRACT IS FAILURE-IS-SILENT: any error (no daemon.json, connection
refused, timeout, non-200, malformed JSON) prints nothing and exits 0. A broken
daemon must never break the user's agent startup. Uses stdlib ``urllib`` (no
heavy deps) with a short timeout.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.daemon.pid_lock import read as _read_daemon_file

#: Short timeout — the hook runs on the critical path of agent startup.
_TIMEOUT = 5.0

#: Dialect values, mirroring ``domain.agent.context_injection.HookFlavor``. Kept
#: as plain literals so this entrypoint stays import-light: it runs on every agent
#: startup and must not drag in the domain package.
_DIALECT_CLAUDE = "claude"
_DIALECT_CURSOR = "cursor"
_DIALECT_RAW = "raw"

#: Event names as each dialect spells them, mapped to Coffer's canonical name.
_EVENT_ALIASES = {
    "sessionstart": "SessionStart",
    "sessionend": "SessionEnd",
}


def _canonical_event(raw: str) -> str:
    """Coffer's canonical event name for a dialect's spelling (``sessionStart``)."""
    return _EVENT_ALIASES.get(raw.casefold(), raw)


def _daemon_json_path() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


def _read_daemon_info() -> DaemonInfo | None:
    """Read ``~/.coffer/daemon.json``; ``None`` if absent or unreadable."""
    path = _daemon_json_path()
    if not path.exists():
        return None
    try:
        return _read_daemon_file(path)
    except (ValueError, KeyError, OSError):
        return None


def _http(
    method: str,
    url: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
    timeout: float,
) -> tuple[int, str]:
    """One blocking HTTP request via stdlib ``urllib``. Returns ``(status, text)``.

    Raises on transport errors (caught by the caller's blanket except).
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Coffer-Token": token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, ""


def _envelope(dialect: str, context: str) -> dict[str, Any]:
    """Wrap the rules bundle in the shape this agent's hook contract expects.

    Cursor's ``sessionStart`` hook reads a top-level ``additional_context``;
    Claude Code and Codex read ``hookSpecificOutput.additionalContext``.
    """
    if dialect == _DIALECT_CURSOR:
        return {"additional_context": context}
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }


def _handle_session_start(agent: str, cwd: str | None, info: DaemonInfo, dialect: str) -> None:
    # OMIT `cwd` rather than sending an empty one when it is unknown. The daemon
    # scopes memory by the nearest git root of `cwd`, and an empty string resolves
    # to the DAEMON's own working directory — a long-lived process that may sit in
    # an unrelated repo. Absent `cwd` is the only value that means "global scope".
    query = urllib.parse.urlencode({"cwd": cwd}) if cwd else ""
    url = f"http://127.0.0.1:{info.port}/api/v1/agents/{agent}/session-context"
    if query:
        url = f"{url}?{query}"
    status, text = _http("GET", url, token=info.token, timeout=_TIMEOUT)
    if status != 200 or not text:
        return
    context = json.loads(text).get("additional_context")
    if not context:
        return
    if dialect == _DIALECT_RAW:
        # No envelope: the consumer is Coffer's own dropped plugin, which pushes
        # this text onto the system prompt verbatim.
        sys.stdout.write(context)
    else:
        sys.stdout.write(json.dumps(_envelope(dialect, context)))
    sys.stdout.flush()


def _handle_session_end(agent: str, cwd: str, session_id: str, info: DaemonInfo) -> None:
    if not session_id:
        return
    url = f"http://127.0.0.1:{info.port}/api/v1/agents/{agent}/sessions/{session_id}/end"
    _http("POST", url, token=info.token, body={"cwd": cwd}, timeout=_TIMEOUT)


def _read_payload() -> dict[str, Any]:
    """The hook's stdin JSON, or ``{}`` when absent or unparseable.

    Callers MUST NOT invoke this when the payload is not needed: ``sys.stdin.read()``
    blocks until EOF, and the 5s timeout bounds only HTTP. An agent that spawns the
    hook with stdin left open would stall its own startup — the one thing this
    entrypoint promises never to do. Claude/Codex always send and close a payload;
    Cursor's is not contractual, so the Cursor path never reads it.
    """
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _process_cwd() -> str | None:
    """The hook process's working directory — it inherits the agent's, which is the
    session's project. ``None`` when it cannot be read (e.g. the directory was
    deleted), so the caller omits `cwd` and the daemon scopes globally."""
    try:
        return os.getcwd()
    except OSError:
        return None


def _dispatch() -> None:
    parser = argparse.ArgumentParser(prog="coffer-hook")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--dialect", default=_DIALECT_CLAUDE)
    parser.add_argument("--event", default=None)
    args, _unknown = parser.parse_known_args()

    # A SessionStart named by --event needs nothing from stdin, so don't read it:
    # a stdin left open by the agent would block until EOF and stall its startup.
    # Every other path (Claude/Codex, or any SessionEnd needing `session_id`)
    # reads the payload, which those agents always send and close.
    known_start = _canonical_event(args.event) == "SessionStart" if args.event else False
    payload = {} if known_start else _read_payload()

    # --event wins: Cursor keys hooks.json by event and does not guarantee an
    # event field on stdin. Claude/Codex omit --event and name it on stdin.
    event = _canonical_event(args.event or payload.get("hook_event_name") or "")
    # The hook inherits the agent's working directory, so the process cwd is the
    # session's project when the payload omits it (Cursor). `None` means unknown —
    # never "", which the daemon would resolve against its OWN cwd.
    cwd = payload.get("cwd") or _process_cwd()
    session_id = payload.get("session_id") or ""

    info = _read_daemon_info()
    if info is None:
        return

    if event == "SessionStart":
        _handle_session_start(args.agent, cwd, info, args.dialect)
    elif event == "SessionEnd":
        _handle_session_end(args.agent, cwd or "", session_id, info)
    # Any other event → nothing to do.


def run() -> None:
    """Entry point for ``coffer-hook``. Always exits 0; never raises."""
    # FAILURE-IS-SILENT: a broken daemon must never break agent startup.
    with contextlib.suppress(Exception):
        _dispatch()
    sys.exit(0)


if __name__ == "__main__":
    run()
