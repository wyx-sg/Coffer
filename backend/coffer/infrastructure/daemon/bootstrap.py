"""Daemon bootstrap: allocate port + generate token + write/remove daemon.json.

ADR-006 (detect-or-spawn) calls for a ``flock`` held while a freshly-spawned
daemon decides whether to bind. :func:`acquire_or_existing` is that critical
section: it takes an exclusive lock on ``~/.coffer/daemon.lock`` and, under it,
probes :func:`live_daemon`, and only if none is live binds a port and writes
``daemon.json``.

Crucially the lock is held PAST the ``daemon.json`` write — until the
freshly-spawned daemon is actually serving HTTP. :func:`acquire_or_existing`
returns a ``release`` callable that the daemon entrypoint invokes only once
uvicorn is listening. Serialising probe+bind+write+**announce-ready** closes the
check-then-act race in which two near-simultaneous auto-spawns each pass the
probe, each bind a different free port, and the second's atomic ``os.replace``
clobbers ``daemon.json`` — orphaning the first daemon. Releasing the lock the
instant daemon.json was written (rather than at serving) left a sub-second boot
window in which a racing spawn ran :func:`live_daemon`, got ``None`` (the port
is bound but not yet answering ``/daemon/status``), and bound a second port.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import socket
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx

from coffer.infrastructure.daemon.pid_lock import DaemonInfo, read, write
from coffer.infrastructure.daemon.port_alloc import bind_free_socket

_DAEMON_JSON_VERSION = 1

#: Releases the spawn lock. Returned by :func:`acquire_or_existing`; the daemon
#: entrypoint calls it once the server is serving HTTP. Idempotent.
ReleaseSpawnLock = Callable[[], None]


def _noop_release() -> None:
    """A release callable for paths that never held (or already freed) the lock."""


# How long to wait when probing whether an existing daemon is reachable.
_LIVENESS_PROBE_TIMEOUT: float = 2.0


def _coffer_dir() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer"


def _daemon_json_path() -> Path:
    return _coffer_dir() / "daemon.json"


def _spawn_lock_path() -> Path:
    return _coffer_dir() / "daemon.lock"


def _acquire_spawn_lock() -> int:
    """Open ``~/.coffer/daemon.lock`` and take an exclusive ``flock``; return fd.

    ADR-006: this is the lock that serialises the probe+bind+write+announce
    critical section so two racing auto-spawns can't both bind. The caller MUST
    eventually free it via :func:`_release_spawn_lock`. On Windows (no
    ``fcntl``) the lock degrades to a bare open fd — the daemon's own
    ``live_daemon`` refusal in ``acquire_or_existing`` plus the atomic
    ``os.replace`` remain as the last line of defence there.

    The lockfile itself is intentionally left on disk between runs — a flock is
    advisory and tied to the open fd, not the file's existence.
    """
    lock_path = _spawn_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        import fcntl
    except ImportError:  # pragma: no cover - Windows fallback
        return fd
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _release_spawn_lock(fd: int) -> None:
    """Release the ``flock`` and close ``fd`` (best-effort; safe if already gone)."""
    try:
        import fcntl
    except ImportError:  # pragma: no cover - Windows fallback
        pass
    else:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
    with contextlib.suppress(OSError):
        os.close(fd)


@contextmanager
def _spawn_lock() -> Iterator[int]:
    """Scoped form of the spawn lock: hold it for the body, release on exit.

    Used where the critical section is fully contained in a ``with`` block.
    :func:`acquire_or_existing` instead holds the lock past its own return (it
    must stay held until the daemon is serving), so it uses the acquire/release
    primitives directly rather than this context manager.
    """
    fd = _acquire_spawn_lock()
    try:
        yield fd
    finally:
        _release_spawn_lock(fd)


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


def acquire_or_existing() -> tuple[DaemonInfo, socket.socket | None, ReleaseSpawnLock]:
    """ADR-006 spawn critical section, under the exclusive spawn lock.

    Takes ``~/.coffer/daemon.lock`` and then:
      1. probes :func:`live_daemon`;
      2. if a daemon is already live, releases the lock and returns
         ``(its info, None, no-op release)`` WITHOUT binding a second port (so
         daemon.json is never clobbered);
      3. otherwise :func:`acquire` a port + write daemon.json and returns
         ``(info, sock, release)`` — **with the lock STILL held**. The caller
         passes the socket's fd to uvicorn and invokes ``release`` only once the
         server is actually serving HTTP.

    Holding the lock across probe+bind+write **and on past the return, until the
    daemon is serving**, is what closes the boot-window race that orphans
    daemons: a racing auto-spawn that wakes mid-boot blocks on the still-held
    lock (rather than probing a bound-but-not-serving port, getting ``None``,
    and binding a second port). The returned ``release`` is idempotent, so the
    entrypoint can also call it from a ``finally`` without double-freeing.
    """
    fd = _acquire_spawn_lock()
    released = False

    def _release() -> None:
        nonlocal released
        if released:
            return
        released = True
        _release_spawn_lock(fd)

    try:
        existing = live_daemon()
        if existing is not None:
            _release()
            return existing, None, _noop_release
        info, sock = acquire()
    except BaseException:
        _release()
        raise
    return info, sock, _release


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
