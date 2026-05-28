"""Daemon bootstrap: allocate port + generate token + write/remove daemon.json."""

from __future__ import annotations

import contextlib
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write
from coffer.infrastructure.daemon.port_alloc import allocate

_DAEMON_JSON_VERSION = 1


def _daemon_json_path() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


def _port_range() -> tuple[int, int]:
    start = int(os.environ.get("COFFER_PORT_RANGE_START", "8000"))
    end = int(os.environ.get("COFFER_PORT_RANGE_END", "8009"))
    return start, end


def acquire() -> DaemonInfo:
    """Allocate port + generate token, then write daemon.json. Caller starts the server."""
    start, end = _port_range()
    port = allocate(start=start, end=end)
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
    return info


def release() -> None:
    """Best-effort removal of daemon.json on shutdown."""
    path = _daemon_json_path()
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)
