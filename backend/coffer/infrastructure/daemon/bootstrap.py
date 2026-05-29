"""Daemon bootstrap: allocate port + generate token + write/remove daemon.json."""

from __future__ import annotations

import contextlib
import os
import secrets
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write
from coffer.infrastructure.daemon.port_alloc import bind_free_socket

_DAEMON_JSON_VERSION = 1


def _daemon_json_path() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


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
