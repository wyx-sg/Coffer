"""Daemon bootstrap: allocate port + generate token + write/remove daemon.json.

The detect-or-spawn ADR calls for a ``flock`` held while a freshly-spawned
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

from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.pid_lock import (
    DaemonInfo,
    pid_is_coffer_daemon,
    read,
    write,
)
from coffer.infrastructure.daemon.port_alloc import bind_fixed_socket, bind_free_socket

_DAEMON_JSON_VERSION = 1

#: Releases the spawn lock. Returned by :func:`acquire_or_existing`; the daemon
#: entrypoint calls it once the server is serving HTTP. Idempotent.
ReleaseSpawnLock = Callable[[], None]


def _noop_release() -> None:
    """A release callable for paths that never held (or already freed) the lock."""


# How long to wait when probing whether an existing daemon is reachable.
#
# This must outlast the SLOWEST ``/daemon/status`` a serving daemon can produce,
# not the typical one. A daemon that has released the spawn lock is still
# finishing its own warm-up (migrations, MCP upstream startup) and has been
# measured taking ~9s to answer; at the old 2s the probe timed out, the spawn
# concluded "nobody is live", and it bound a SECOND port beside a perfectly
# healthy daemon — the failure that filled 8000-8009 one restart at a time. A
# generous timeout costs nothing in the common failure case: a stale daemon.json
# points at a port nobody is listening on, which refuses the connection at once
# rather than timing out.
_LIVENESS_PROBE_TIMEOUT: float = 15.0


def _coffer_dir() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer"


def _daemon_json_path() -> Path:
    return _coffer_dir() / "daemon.json"


def _spawn_lock_path() -> Path:
    return _coffer_dir() / "daemon.lock"


def _acquire_spawn_lock() -> int:
    """Open ``~/.coffer/daemon.lock`` and take an exclusive ``flock``; return fd.

    Detect-or-spawn: this is the lock that serialises the probe+bind+write+announce
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

    Detect-or-spawn: a freshly-spawned daemon calls this *before* binding so it
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


def superseded_by() -> DaemonInfo | None:
    """The OTHER live daemon that now owns ``daemon.json``, or ``None``.

    :func:`live_daemon` guards the spawn from one side, but it only ever probes
    the single port recorded in daemon.json — it cannot see a daemon alive on a
    different port. Whenever that probe fails while a daemon is in fact running
    (daemon.json deleted, or a serving-but-busy daemon that missed the probe
    timeout), the spawn binds the next free port and the older daemon runs on
    forever holding its own. Repeat and the whole 8000-8009 range is consumed,
    after which no daemon can start at all.

    This is the other side of that guard: a daemon calls it periodically and
    stands down once it can see that it has been superseded. The conditions are
    deliberately narrow — it fires ONLY when daemon.json exists, names a pid
    that is not ours, and that pid is a live Coffer daemon:

    * an absent daemon.json must never evict anyone (otherwise deleting the file
      would take the one healthy daemon down with it);
    * a malformed one is no evidence of anything;
    * a recorded pid that is dead, recycled, or not a Coffer daemon means we are
      still the only daemon alive — the next spawn will replace us in an orderly
      way.

    So a group of daemons converges on exactly the one daemon.json names, and a
    lone daemon whose discovery file is missing or stale keeps serving.
    """
    try:
        info = read(_daemon_json_path())
    except (FileNotFoundError, ValueError, KeyError, OSError):
        return None
    if info.pid == os.getpid():
        return None
    return info if pid_is_coffer_daemon(info.pid) else None


#: The scan range used when the user has fixed no port and the environment
#: names none. 8000 first, because that is the port every surface's
#: documentation and every existing bookmark already says.
_DEFAULT_PORT_RANGE = (8000, 8009)


def _env_port_range() -> tuple[int, int] | None:
    """An explicit range from the environment, or ``None``.

    This is the test harness's hook — every test that starts a real daemon
    pins its own disjoint range here so concurrent tests cannot collide — and
    it deliberately outranks the user's fixed port, so a test run is hermetic
    on a machine whose vault has one configured.
    """
    start = os.environ.get("COFFER_PORT_RANGE_START")
    end = os.environ.get("COFFER_PORT_RANGE_END")
    if start is None and end is None:
        return None
    return int(start or _DEFAULT_PORT_RANGE[0]), int(end or _DEFAULT_PORT_RANGE[1])


def _bind_port() -> socket.socket:
    """Bind the daemon's listening socket, honouring the user's fixed port.

    Precedence: the environment's explicit range (tests), then the fixed port
    the user configured (spec mcp-gateway FR-028), then the default scan. The
    fixed path raises :class:`~coffer.infrastructure.daemon.port_alloc.PortInUse`
    rather than falling back — the entrypoint turns that into a refusal to
    start, which is the whole point of fixing a port.
    """
    env_range = _env_port_range()
    if env_range is not None:
        return bind_free_socket(start=env_range[0], end=env_range[1])
    fixed = daemon_config.read_fixed_port()
    if fixed is not None:
        return bind_fixed_socket(fixed)
    return bind_free_socket(start=_DEFAULT_PORT_RANGE[0], end=_DEFAULT_PORT_RANGE[1])


def acquire() -> tuple[DaemonInfo, socket.socket]:
    """Bind a free port + generate token, then write daemon.json.

    Returns ``(info, sock)``. CODE-041: the caller MUST keep ``sock`` open and
    pass its fd to the server (uvicorn ``fd=sock.fileno()``) so the port is
    never released between publishing ``daemon.json`` and the server binding.
    The caller closes ``sock`` when the server stops.

    Prefer :func:`acquire_or_existing`, which wraps this in the detect-or-spawn
    lock together with the duplicate-daemon probe. ``acquire`` is kept as the
    lock-free primitive (and is called by ``acquire_or_existing`` while the
    lock is held).
    """
    sock = _bind_port()
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
    """Detect-or-spawn critical section, under the exclusive spawn lock.

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
