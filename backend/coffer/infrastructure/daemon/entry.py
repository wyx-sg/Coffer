"""Daemon entry — what `coffer daemon start` spawns.

Port allocation happens HERE, before uvicorn binds, so that:
1. bootstrap.acquire_or_existing() takes the spawn lock, picks a free port,
   writes daemon.json, and returns the pre-bound socket plus a `release`
   callable for that lock (still held).
2. _run_server() hands the socket fd to uvicorn and releases the spawn lock
   only once uvicorn reports it is serving (ADR-006 boot-window fix) — so a
   racing auto-spawn can't bind a second port mid-boot and orphan this daemon.
3. The FastAPI lifespan in app.py reads daemon.json (already present) and
   calls set_active_token / set_port to wire up auth and status reporting.

This module intentionally imports ONLY from coffer.infrastructure to
satisfy the "Infrastructure does not import surfaces" contract.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import socket
import sys
from collections.abc import Callable

import uvicorn

from coffer.infrastructure.daemon import bootstrap

_logger = logging.getLogger(__name__)

# How often _run_server polls uvicorn's ``started`` flag while waiting to
# release the spawn lock. Small enough that the post-listen lock-hold is
# imperceptible, large enough not to busy-spin.
_STARTED_POLL_INTERVAL = 0.02

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


def _install_signal_handlers() -> None:
    def _term(_sig: int, _frame: object) -> None:
        bootstrap.release()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)


def _run_server(sock: socket.socket, on_started: Callable[[], None]) -> None:
    """Serve the app on the pre-bound loopback fd; call ``on_started`` once the
    server is actually serving HTTP (uvicorn ``Server.started``).

    ADR-006 boot-window fix: ``on_started`` releases the spawn lock. Releasing
    it here — only after uvicorn has called ``listen()`` and is accepting — not
    when daemon.json was written, means a racing auto-spawn that probes
    ``/daemon/status`` either blocks on the still-held lock or sees a
    fully-serving daemon, never a half-bound one. If startup fails (serve
    returns/raises before ``started``), ``on_started`` still fires in the
    ``finally`` so the lock is never leaked into a deadlock for the next spawn.

    No host/port is passed: binding is owned by the pre-bound loopback fd
    (CODE-041), so nothing can widen the daemon off 127.0.0.1.
    """
    config = uvicorn.Config(
        "coffer.main:app",
        fd=sock.fileno(),
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    async def _runner() -> None:
        serve_task = asyncio.ensure_future(server.serve())
        try:
            while not server.started and not serve_task.done():
                await asyncio.sleep(_STARTED_POLL_INTERVAL)
        finally:
            on_started()
        await serve_task

    asyncio.run(_runner())


def main() -> None:
    # sqlite-vec availability is reported by the daemon's /daemon/status endpoint
    # (vec_available) and asserted by the bundle smoke test against the running
    # frozen binary — not via an argv probe here, so this module never imports
    # the knowledge engine (engine-confinement contract).
    _raise_fd_soft_limit()
    _install_signal_handlers()
    # ADR-006: probe + bind happen under one flock (acquire_or_existing). If a
    # daemon is already reachable, sock is None and we exit cleanly so the
    # auto-spawn caller (CLI/shim) discovers it; otherwise we hold the bound
    # socket AND the spawn lock — release_lock frees the lock only once we are
    # serving (passed to _run_server as on_started), so a racing auto-spawn
    # can't bind a second port during the boot window and orphan a daemon.
    info, sock, release_lock = bootstrap.acquire_or_existing()
    if sock is None:
        _logger.info(
            "daemon already running (pid=%s, port=%s); exiting",
            info.pid,
            info.port,
        )
        return
    # CODE-041: acquire() binds the port and hands us the live socket; passing
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
