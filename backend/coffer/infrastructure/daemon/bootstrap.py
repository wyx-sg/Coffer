"""Daemon bootstrap: allocate port + generate token + write/remove daemon.json.

ADR-006 (detect-or-spawn) calls for a ``flock`` held while a freshly-spawned
daemon decides whether to bind. :func:`acquire_or_existing` is that critical
section: it takes an exclusive lock on ``~/.coffer/daemon.lock`` and, under it,
probes :func:`live_daemon`, and only if none is live binds a port and writes
``daemon.json``. Serialising probe+bind+write closes the check-then-act race in
which two near-simultaneous auto-spawns each pass the probe, each bind a
different free port, and the second's atomic ``os.replace`` clobbers
``daemon.json`` — orphaning the first daemon.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx

from coffer.infrastructure.daemon.pid_lock import DaemonInfo, read, write
from coffer.infrastructure.daemon.port_alloc import bind_free_socket

_DAEMON_JSON_VERSION = 1

# How long to wait when probing whether an existing daemon is reachable.
_LIVENESS_PROBE_TIMEOUT: float = 2.0


def _coffer_dir() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer"


def _daemon_json_path() -> Path:
    return _coffer_dir() / "daemon.json"


def _spawn_lock_path() -> Path:
    return _coffer_dir() / "daemon.lock"


@contextmanager
def _spawn_lock() -> Iterator[int]:
    """Hold an exclusive ``flock`` on ``~/.coffer/daemon.lock`` for the body.

    ADR-006: this is the lock that serialises the probe+bind+write critical
    section so two racing auto-spawns can't both bind. On Windows (no
    ``fcntl``) the lock degrades to a no-op — the daemon's own
    ``live_daemon`` refusal in ``acquire_or_existing`` plus the atomic
    ``os.replace`` remain as the last line of defence there.

    Yields the held lockfile fd; the lock is released (and the fd closed) on
    exit. The lockfile itself is intentionally left on disk between runs — a
    flock is advisory and tied to the open fd, not the file's existence.
    """
    lock_path = _spawn_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        import fcntl
    except ImportError:  # pragma: no cover - Windows fallback
        try:
            yield fd
        finally:
            os.close(fd)
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def live_daemon() -> DaemonInfo | None:
    """Return the running daemon's info iff daemon.json exists AND a *Coffer*
    daemon answers on its recorded port; otherwise ``None`` (absent,
    malformed, stale, or a foreign listener).

    ADR-006: a freshly-spawned daemon calls this *before* binding so it
    refuses to start a duplicate when one is already serving. Without this
    guard, two near-simultaneous auto-spawns (CLI + shim, or two clients) each
    bind a different free port and the second's ``os.replace`` clobbers
    daemon.json — orphaning the first daemon. The probe runs under the spawn
    lock (see :func:`acquire_or_existing`) so the decision is atomic with the
    bind that follows it.

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

    Prefer :func:`acquire_or_existing`, which wraps this in the ADR-006 spawn
    lock together with the duplicate-daemon probe. ``acquire`` is kept as the
    lock-free primitive (and is called by ``acquire_or_existing`` while the
    lock is held).
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


def acquire_or_existing() -> tuple[DaemonInfo, socket.socket | None]:
    """ADR-006 spawn critical section, under the exclusive spawn lock.

    Under ``~/.coffer/daemon.lock``:
      1. probe :func:`live_daemon`;
      2. if a daemon is already live, return ``(its info, None)`` WITHOUT
         binding a second port (so daemon.json is never clobbered);
      3. otherwise :func:`acquire` a port + write daemon.json and return
         ``(info, sock)`` with the held socket.

    Holding the lock across probe+bind+write is what closes the
    check-then-act race that orphans daemons; the caller passes the returned
    socket's fd to uvicorn (when non-None) or exits cleanly (when None).
    """
    with _spawn_lock():
        existing = live_daemon()
        if existing is not None:
            return existing, None
        return acquire()


def release() -> None:
    """Remove daemon.json on shutdown — but ONLY if it still records our pid.

    A daemon orphaned by a racing spawn (its daemon.json already clobbered to
    point at the winner) must not delete the *live* daemon's discovery file on
    its way out. We read the pid first and unlink only when it is ours; an
    absent or malformed file is left untouched.
    """
    path = _daemon_json_path()
    try:
        info = read(path)
    except (FileNotFoundError, ValueError, KeyError, OSError):
        return  # absent or malformed → nothing we can prove is ours
    if info.pid != os.getpid():
        return  # belongs to another (live) daemon — do not clobber
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)
