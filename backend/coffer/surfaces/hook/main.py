"""``coffer-hook`` — the agent session-lifecycle → Coffer-daemon bridge.

Spawned by the agent (Claude Code / Codex) as a SessionStart / SessionEnd hook.
Reads the hook JSON from stdin and the Coffer agent name from ``--agent <name>``
(the hook payload does not carry Coffer's agent identity), then talks to the
local daemon discovered via ``~/.coffer/daemon.json``:

- **SessionStart** → ``GET /api/v1/agents/{agent}/session-context?cwd=<cwd>``;
  on 200 print ``{"hookSpecificOutput": {"hookEventName": "SessionStart",
  "additionalContext": <text>}}`` so the agent injects the rules bundle.
- **SessionEnd** → ``POST /api/v1/agents/{agent}/sessions/{session_id}/end``
  with ``{"cwd": cwd}``; the body is ignored.

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


def _handle_session_start(agent: str, cwd: str, info: DaemonInfo) -> None:
    query = urllib.parse.urlencode({"cwd": cwd})
    url = f"http://127.0.0.1:{info.port}/api/v1/agents/{agent}/session-context?{query}"
    status, text = _http("GET", url, token=info.token, timeout=_TIMEOUT)
    if status != 200 or not text:
        return
    context = json.loads(text).get("additional_context")
    if not context:
        return
    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()


def _handle_session_end(agent: str, cwd: str, session_id: str, info: DaemonInfo) -> None:
    if not session_id:
        return
    url = f"http://127.0.0.1:{info.port}/api/v1/agents/{agent}/sessions/{session_id}/end"
    _http("POST", url, token=info.token, body={"cwd": cwd}, timeout=_TIMEOUT)


def _dispatch() -> None:
    parser = argparse.ArgumentParser(prog="coffer-hook")
    parser.add_argument("--agent", required=True)
    args, _unknown = parser.parse_known_args()

    payload = json.loads(sys.stdin.read())
    event = payload.get("hook_event_name")
    cwd = payload.get("cwd") or ""
    session_id = payload.get("session_id") or ""

    info = _read_daemon_info()
    if info is None:
        return

    if event == "SessionStart":
        _handle_session_start(args.agent, cwd, info)
    elif event == "SessionEnd":
        _handle_session_end(args.agent, cwd, session_id, info)
    # Any other event → nothing to do.


def run() -> None:
    """Entry point for ``coffer-hook``. Always exits 0; never raises."""
    # FAILURE-IS-SILENT: a broken daemon must never break agent startup.
    with contextlib.suppress(Exception):
        _dispatch()
    sys.exit(0)


if __name__ == "__main__":
    run()
