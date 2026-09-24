"""Daemon entry — what `coffer daemon start` spawns.

Port allocation happens HERE, before uvicorn binds, so that:
1. bootstrap.acquire_or_existing() takes the spawn lock, picks a free port,
   writes daemon.json, and returns the pre-bound socket plus a `release`
   callable for that lock (still held).
2. _run_server() hands the socket fd to uvicorn and releases the spawn lock
   only once uvicorn reports it is serving (detect-or-spawn boot-window fix) — so a
   racing auto-spawn can't bind a second port mid-boot and orphan this daemon.
3. The FastAPI lifespan in app.py reads daemon.json (already present) and
   calls set_active_token / set_port to wire up auth and status reporting.

This module intentionally imports ONLY from coffer.infrastructure to
satisfy the "Infrastructure does not import surfaces" contract.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import socket
import sys
from collections.abc import Callable, MutableMapping

import uvicorn

from coffer.domain.agent.descriptor import AGENT_DESCRIPTORS
from coffer.infrastructure.daemon import activity, bootstrap
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.port_alloc import PortInUse

_logger = logging.getLogger(__name__)

# How often _run_server polls uvicorn's ``started`` flag while waiting to
# release the spawn lock. Small enough that the post-listen lock-hold is
# imperceptible, large enough not to busy-spin.
_STARTED_POLL_INTERVAL = 0.02

# How often a serving daemon re-reads daemon.json to see whether another daemon
# has taken it over (detect-or-spawn amendment). Long enough to be free, short
# that an orphan cannot linger through a work session holding its port.
_ORPHAN_CHECK_INTERVAL = 30.0

# How often the idle watcher looks at the clock. The window it is comparing
# against is measured in hours, so a minute's granularity costs nothing and
# keeps a sleeping daemon's wakeups down to one a minute.
_IDLE_CHECK_INTERVAL = 60.0

# How long a shutdown waits for open connections before closing them itself.
# Without a bound, uvicorn's graceful shutdown waits forever on a connection
# that never ends — and this daemon serves `/mcp` over SSE, which is exactly
# such a connection. A stand-down or a restart that stopped accepting and then
# hung would be worse than either: launchd would not restart it (nothing
# exited) and the next client would find a port that no longer answers.
_SHUTDOWN_GRACE_SECONDS = 10

# Ceiling for the RLIMIT_NOFILE soft limit we raise at startup. Comfortably
# above what a healthy daemon needs (sqlite + uvicorn socket + channel
# listeners + ~2 pipe fds per live stdio upstream) so transient spikes never
# reach it, without asking for an unbounded fd table.
_FD_SOFT_LIMIT_TARGET = 8192


def _raise_fd_soft_limit() -> None:
    """Raise this daemon's RLIMIT_NOFILE soft limit toward its hard limit.

    Launched from a macOS GUI app via launchd, the daemon inherits a soft
    file-descriptor limit of ~256. That ceiling is reachable in normal use, and
    any fd leak (see mcp/subprocess.py ``_cleanup``) turns it into a hard crash
    where every subprocess spawn and socket accept fails with
    ``OSError: [Errno 24] Too many open files`` — surfaced to the UI as the
    opaque "upstream init failed: OSError". Lift the soft limit to the hard
    limit (capped at ``_FD_SOFT_LIMIT_TARGET``) so the daemon has real headroom.
    POSIX-only and best-effort: never let an rlimit hiccup stop the daemon from
    booting.
    """
    try:
        import resource
    except ImportError:  # non-POSIX platform — no RLIMIT_NOFILE to raise
        return
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        cap = _FD_SOFT_LIMIT_TARGET
        target = cap if hard == resource.RLIM_INFINITY else min(hard, cap)
        if soft != resource.RLIM_INFINITY and soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            _logger.info("raised RLIMIT_NOFILE soft limit %s -> %s", soft, target)
    except (ValueError, OSError) as exc:  # pragma: no cover - platform dependent
        _logger.warning("could not raise RLIMIT_NOFILE soft limit: %r", exc)


def scrub_agent_home_env(environ: MutableMapping[str, str]) -> list[str]:
    """Remove every agent-home variable (``CLAUDE_CONFIG_DIR``, ``CODEX_HOME``)
    the daemon inherited, and log once which ones went.

    A daemon started from a shell that exports one of them would pass it to
    every agent process it spawns — so an agent registered on the default
    directory would run against the exported one while Coffer delivers skills,
    the MCP entry and config into the default. Agents get the variable only
    through their own registered config directory (``AgentConfig.runtime_env``),
    per spec daemon "Clear inherited agent-home variables at start". The names
    come from the agent descriptors, so a new agent type's variable is covered
    without touching this list.
    """
    names = sorted({d.home_env_var for d in AGENT_DESCRIPTORS.values() if d.home_env_var})
    removed = [name for name in names if environ.pop(name, None) is not None]
    if removed:
        # WARNING, not INFO: this runs before the app configures logging, and
        # only WARNING and above reach stderr (the daemon log) at that point.
        _logger.warning(
            "cleared inherited agent-home variables %s; agents get them only "
            "from their registered config directory",
            ", ".join(removed),
        )
    return removed


def _install_signal_handlers() -> None:
    def _term(_sig: int, _frame: object) -> None:
        bootstrap.release()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)


async def _evict_when_superseded(
    server: uvicorn.Server, *, interval: float = _ORPHAN_CHECK_INTERVAL
) -> None:
    """Stand down once ``daemon.json`` names a different, live Coffer daemon.

    The detect-or-spawn guard only ever probes the one port daemon.json records, so
    a spawn that cannot see us (the file was lost, or we were too busy to answer
    the liveness probe) binds a second port and leaves us running. Nothing ever
    reclaimed that port: ``orphan_sweep.reap_stale_daemons`` no-ops outside
    frozen builds, so a run-from-source setup accumulated one orphan per restart
    until 8000-8009 were full and no daemon could start at all.

    Watching from this side needs no cross-process authority: we only ever stop
    OURSELVES, and only on positive evidence that someone else is now the
    daemon. :func:`bootstrap.superseded_by` is deliberately narrow about what
    counts, so an absent or stale daemon.json leaves a lone daemon serving.

    The check is best-effort — an unreadable file or a psutil hiccup must not
    take a healthy daemon down, so it is logged and retried, never acted on.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            superseded = bootstrap.superseded_by()
        except Exception:
            _logger.warning("daemon supersession check failed; still serving", exc_info=True)
            continue
        if superseded is None:
            continue
        _logger.warning(
            "daemon superseded by pid=%s on port=%s; shutting down to free this port",
            superseded.pid,
            superseded.port,
        )
        server.should_exit = True
        return


async def _stand_down_when_idle(
    server: uvicorn.Server,
    *,
    idle_window_seconds: float,
    interval: float = _IDLE_CHECK_INTERVAL,
) -> None:
    """Exit cleanly once nothing has wanted this daemon for long enough.

    The counterpart to being a login service. launchd starts the daemon at
    login and restarts it when it dies badly, which is what makes an agent's
    ``coffer__*`` call work at any hour without an app being open; this is what
    stops that turning into a process that outlives every reason for it.

    Standing down is a NORMAL exit, and that is the whole contract with
    launchd: the service is installed with ``KeepAlive`` restricted to
    unsuccessful exits, so a clean stand-down stays down and a crash does not.
    Getting that backwards would make this a restart loop rather than a
    shutdown. Whoever next wants a daemon — the app, the CLI, an agent's MCP
    shim — starts one, which every one of them already knows how to do.

    What counts as "wanted" is :mod:`coffer.infrastructure.daemon.activity`:
    requests that reached the application, plus holds from subsystems whose
    job is to be reachable rather than to be called (the channel listener).
    """
    while True:
        await asyncio.sleep(interval)
        idle = activity.idle_seconds()
        if idle < idle_window_seconds:
            continue
        _logger.info(
            "daemon idle for %.0fs (window %.0fs); standing down",
            idle,
            idle_window_seconds,
        )
        server.should_exit = True
        return


def _run_server(sock: socket.socket, on_started: Callable[[], None]) -> None:
    """Serve the app on the pre-bound loopback fd; call ``on_started`` once the
    server is actually serving HTTP (uvicorn ``Server.started``).

    Detect-or-spawn boot-window fix: ``on_started`` releases the spawn lock. Releasing
    it here — only after uvicorn has called ``listen()`` and is accepting — not
    when daemon.json was written, means a racing auto-spawn that probes
    ``/daemon/status`` either blocks on the still-held lock or sees a
    fully-serving daemon, never a half-bound one. If startup fails (serve
    returns/raises before ``started``), ``on_started`` still fires in the
    ``finally`` so the lock is never leaked into a deadlock for the next spawn.

    No host/port is passed: binding is owned by the pre-bound loopback fd
    (spec daemon "Bind every endpoint to loopback only"), so nothing can
    widen the daemon off 127.0.0.1.
    """
    config = uvicorn.Config(
        "coffer.main:app",
        fd=sock.fileno(),
        log_level="warning",
        access_log=False,
        timeout_graceful_shutdown=_SHUTDOWN_GRACE_SECONDS,
    )
    server = uvicorn.Server(config)

    async def _runner() -> None:
        serve_task = asyncio.ensure_future(server.serve())
        try:
            while not server.started and not serve_task.done():
                await asyncio.sleep(_STARTED_POLL_INTERVAL)
        finally:
            on_started()
        # Only now that the spawn lock is freed can another daemon take
        # daemon.json from us, so the watcher starts here rather than at boot.
        evictor = asyncio.create_task(_evict_when_superseded(server), name="daemon-orphan-evictor")
        # Unset means "never stand down" — the setting for someone whose
        # channels must answer at any hour (spec daemon "Stand down after an
        # idle window").
        idle_hours = daemon_config.read_idle_shutdown_hours()
        idler = (
            None
            if idle_hours is None
            else asyncio.create_task(
                _stand_down_when_idle(server, idle_window_seconds=idle_hours * 3600.0),
                name="daemon-idle-watcher",
            )
        )
        try:
            await serve_task
        finally:
            for task in (evictor, idler):
                if task is None:
                    continue
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    asyncio.run(_runner())


def main() -> None:
    # First, before anything can spawn an agent process that inherits them.
    scrub_agent_home_env(os.environ)
    _raise_fd_soft_limit()
    _install_signal_handlers()
    # Detect-or-spawn: probe + bind happen under one flock (acquire_or_existing). If a
    # daemon is already reachable, sock is None and we exit cleanly so the
    # auto-spawn caller (CLI/shim) discovers it; otherwise we hold the bound
    # socket AND the spawn lock — release_lock frees the lock only once we are
    # serving (passed to _run_server as on_started), so a racing auto-spawn
    # can't bind a second port during the boot window and orphan a daemon.
    try:
        info, sock, release_lock = bootstrap.acquire_or_existing()
    except PortInUse as exc:
        # The user fixed this port precisely so it would not move, so there is
        # nothing sensible to fall back to. Say what holds it and stop. stderr
        # is the daemon log when we were spawned detached, and the terminal
        # when the user ran us directly; `coffer daemon start` makes the same
        # diagnosis itself so the common path shows this without opening a log.
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None
    if sock is None:
        _logger.info(
            "daemon already running (pid=%s, port=%s); exiting",
            info.pid,
            info.port,
        )
        return
    # acquire() binds the port and hands us the live socket; passing
    # its fd to uvicorn means there is no close-then-rebind window in which the
    # port (already published in daemon.json with the token) could be stolen.
    # That also removes the old EADDRINUSE retry loop entirely — we own the
    # socket, so uvicorn cannot fail to bind it.
    try:
        _run_server(sock, release_lock)
    finally:
        # Single release site (normal shutdown / uvicorn return); the SIGTERM
        # handler covers signalled termination. release_lock is idempotent, so
        # if startup failed before serving it was already freed here-or-there.
        release_lock()
        bootstrap.release()
        sock.close()


if __name__ == "__main__":
    main()
