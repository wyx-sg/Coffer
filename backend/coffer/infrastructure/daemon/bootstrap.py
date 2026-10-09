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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.pid_lock import (
    DaemonInfo,
    pid_is_coffer_daemon,
    read,
    write,
)
from coffer.infrastructure.daemon.port_alloc import bind_fixed_socket, bind_free_socket
from coffer.infrastructure.daemon.spawn_lock import (
    SPAWN_LOCK_TIMEOUT_SECONDS,
    SpawnLockBusy,
)
from coffer.infrastructure.daemon.spawn_lock import acquire_spawn_lock as _acquire_spawn_lock
from coffer.infrastructure.daemon.spawn_lock import release_spawn_lock as _release_spawn_lock
from coffer.infrastructure.daemon.spawn_lock import spawn_lock_path as _spawn_lock_path
from coffer.infrastructure.vault.home import daemon_json_path

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
# healthy daemon — the failure that filled 8000-8009 one restart at a time back
# when a start could scan, and that now surfaces as a spawn refusing the one
# port its healthy predecessor already holds. A generous timeout costs nothing
# in the common failure case: a stale daemon.json
# points at a port nobody is listening on, which refuses the connection at once
# rather than timing out.
_LIVENESS_PROBE_TIMEOUT: float = 15.0


def _daemon_json_path() -> Path:
    return daemon_json_path()


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
    return info if probe_status(info) is not None else None


def probe_status(
    info: DaemonInfo, *, timeout: float = _LIVENESS_PROBE_TIMEOUT
) -> dict[str, Any] | None:
    """The ``/daemon/status`` body of the daemon ``info`` names, or ``None``
    when nothing answers 200 there.

    The single probe behind :func:`live_daemon`; callers that also want the
    body — the CLI and shim compare its ``version`` with their own build — use
    it directly. A 200 whose body is not a JSON object still counts as live
    (an empty dict), so a liveness decision never hinges on the payload.
    """
    try:
        resp = httpx.get(
            f"http://127.0.0.1:{info.port}/api/v1/daemon/status",
            timeout=timeout,
        )
    except httpx.HTTPError:
        return None  # not reachable / not speaking HTTP → no live daemon
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def superseded_by() -> DaemonInfo | None:
    """The OTHER live daemon that now owns ``daemon.json``, or ``None``.

    :func:`live_daemon` guards the spawn from one side, but it only ever probes
    the single port recorded in daemon.json — it cannot see a daemon alive on a
    different port. Whenever that probe fails while a daemon is in fact running
    (daemon.json deleted, or a serving-but-busy daemon that missed the probe
    timeout), the spawn cannot see the older daemon at all. Under the test
    harness's range override it binds the next free port and both run on
    forever; on a normal start it now collides with the older daemon's port and
    refuses outright — clearer, but still not a daemon standing down.

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


#: The range the environment override falls back to when it names only one
#: end of it. Not a default the daemon ever reaches on its own: a start with
#: no override binds exactly one port (see :func:`_bind_port`).
_OVERRIDE_PORT_RANGE_FALLBACK = (daemon_config.DEFAULT_PORT, daemon_config.DEFAULT_PORT + 9)


def _env_port_range() -> tuple[int, int] | None:
    """An explicit range from the environment, or ``None``.

    This is the test harness's hook — every test that starts a real daemon
    pins its own disjoint range here so concurrent tests cannot collide on the
    one port a real start now insists on — and it deliberately outranks the
    user's setting, so a test run is hermetic on a machine whose vault has a
    port configured.
    """
    start = os.environ.get("COFFER_PORT_RANGE_START")
    end = os.environ.get("COFFER_PORT_RANGE_END")
    if start is None and end is None:
        return None
    return (
        int(start or _OVERRIDE_PORT_RANGE_FALLBACK[0]),
        int(end or _OVERRIDE_PORT_RANGE_FALLBACK[1]),
    )


def _bind_port() -> socket.socket:
    """Bind the daemon's listening socket: one port, or nothing.

    Precedence: the environment's explicit range (the test harness's override,
    the only path that still scans), otherwise the port
    :func:`~coffer.infrastructure.daemon.config.effective_port` names — the one
    the user pinned, or 38470 when they pinned none.

    The second path raises
    :class:`~coffer.infrastructure.daemon.port_alloc.PortInUse` rather than
    moving elsewhere, and the entrypoint turns that into a refusal to start.
    That refusal is the point: a daemon that relocates itself silently breaks
    the bookmark and the origin-keyed browser state of the UI it serves, and
    nothing shows the user why.
    """
    env_range = _env_port_range()
    if env_range is not None:
        return bind_free_socket(start=env_range[0], end=env_range[1])
    return bind_fixed_socket(daemon_config.effective_port())


def planned_port() -> int | None:
    """The one port the next start will insist on, or ``None`` if it will scan.

    Lets a caller diagnose a conflict *before* spawning without duplicating
    :func:`_bind_port`'s precedence. ``None`` says the environment's range
    override is in play — a test harness — where there is no single port to
    check ahead of time.
    """
    if _env_port_range() is not None:
        return None
    return daemon_config.effective_port()


def acquire() -> tuple[DaemonInfo, socket.socket]:
    """Bind the daemon's port + generate token, then write daemon.json.

    Returns ``(info, sock)``. The caller MUST keep ``sock`` open and
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


def release_for(pid: int) -> None:
    """Remove daemon.json if it still records ``pid`` — for a caller that
    killed that daemon, which could not remove its own file on the way out."""
    path = _daemon_json_path()
    try:
        info = read(path)
    except (FileNotFoundError, ValueError, KeyError, OSError):
        return
    if info.pid == pid:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)


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


__all__ = [
    "SPAWN_LOCK_TIMEOUT_SECONDS",
    "SpawnLockBusy",
    "_acquire_spawn_lock",
    "_release_spawn_lock",
    "_spawn_lock_path",
    "acquire",
    "acquire_or_existing",
    "live_daemon",
    "planned_port",
    "probe_status",
    "release",
    "release_for",
    "superseded_by",
]
