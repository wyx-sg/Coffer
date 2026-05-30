"""Daemon bootstrap: allocate port + generate token + write/remove daemon.json."""

from __future__ import annotations

import contextlib
import os
import secrets
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from coffer.infrastructure.daemon.pid_lock import DaemonInfo, read, write
from coffer.infrastructure.daemon.port_alloc import bind_free_socket

_DAEMON_JSON_VERSION = 1

# How long to wait when probing whether an existing daemon is reachable.
_LIVENESS_PROBE_TIMEOUT: float = 2.0


def _daemon_json_path() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


def live_daemon() -> DaemonInfo | None:
    """Return the running daemon's info iff daemon.json exists AND a *Coffer*
    daemon answers on its recorded port; otherwise ``None`` (absent,
    malformed, stale, or a foreign listener).

    ADR-006: a freshly-spawned daemon calls this *before* binding so it
    refuses to start a duplicate when one is already serving. Without this
    guard, two near-simultaneous auto-spawns (CLI + shim, or two clients) each
    bind a different free port and the second's ``os.replace`` clobbers
    daemon.json — orphaning the first daemon.

    Confirmation hits the auth-exempt ``/daemon/status`` endpoint (the same
    probe the shim's ``_wait_for_daemon`` uses), NOT a bare TCP connect: after
    a crash, an unrelated process can squat the recorded port, and a TCP-only
    probe would false-positive on it and wrongly block startup (and leave
    daemon.json pointing at the foreign listener).
    """
    path = _daemon_json_path()
    if not path.exists():
        return None
    try:
        info = read(path)
    except (ValueError, KeyError, OSError):
        return None  # malformed/stale → treat as no daemon
    try:
        resp = httpx.get(
            f"http://127.0.0.1:{info.port}/api/v1/daemon/status",
            timeout=_LIVENESS_PROBE_TIMEOUT,
        )
    except httpx.HTTPError:
        return None  # not reachable / not speaking HTTP → no live daemon
    return info if resp.status_code == 200 else None


def _port_range() -> tuple[int, int]:
    start = int(os.environ.get("COFFER_PORT_RANGE_START", "8000"))
    end = int(os.environ.get("COFFER_PORT_RANGE_END", "8009"))
    return start, end


def acquire() -> tuple[DaemonInfo, socket.socket]:
    """Bind a free port + generate token, then write daemon.json.

    Returns ``(info, sock)``. CODE-041: the caller MUST keep ``sock`` open and
    pass its fd to the server (uvicorn ``fd=sock.fileno()``) so the port is
    never released between publishing ``daemon.json`` and the server binding.
    The caller closes ``sock`` when the server stops.
    """
    start, end = _port_range()
    sock = bind_free_socket(start=start, end=end)
    port = sock.getsockname()[1]
    token = secrets.token_urlsafe(32)
    info = DaemonInfo(
        version=_DAEMON_JSON_VERSION,
        pid=os.getpid(),
        port=port,
        token=token,
        started_at=datetime.now(tz=UTC),
        binary_path=sys.executable,
    )
    write(_daemon_json_path(), info)
    return info, sock


def release() -> None:
    """Best-effort removal of daemon.json on shutdown."""
    path = _daemon_json_path()
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)
