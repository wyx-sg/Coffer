"""Daemon entry — what `coffer daemon start` spawns.

Port allocation happens HERE, before uvicorn binds, so that:
1. bootstrap.acquire() picks a free port and writes daemon.json.
2. uvicorn.run() binds to exactly that port.
3. The FastAPI lifespan in app.py reads daemon.json (already present) and
   calls set_active_token / set_port to wire up auth and status reporting.

This module intentionally imports ONLY from coffer.infrastructure to
satisfy the "Infrastructure does not import surfaces" contract.
"""

from __future__ import annotations

import logging
import signal
import sys

import uvicorn

from coffer.infrastructure.daemon import bootstrap

_logger = logging.getLogger(__name__)


def _install_signal_handlers() -> None:
    def _term(_sig: int, _frame: object) -> None:
        bootstrap.release()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)


def main() -> None:
    # sqlite-vec availability is reported by the daemon's /daemon/status endpoint
    # (vec_available) and asserted by the bundle smoke test against the running
    # frozen binary — not via an argv probe here, so this module never imports
    # the knowledge engine (engine-confinement contract).
    _install_signal_handlers()
    # ADR-006: probe + bind happen under one flock (acquire_or_existing). If a
    # daemon is already reachable, sock is None and we exit cleanly so the
    # auto-spawn caller (CLI/shim) discovers it; otherwise we hold the bound
    # socket. Serialising probe+bind under the lock is what stops two racing
    # auto-spawns both binding and clobbering daemon.json (orphaning one).
    info, sock = bootstrap.acquire_or_existing()
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
        uvicorn.run(
            "coffer.main:app",
            fd=sock.fileno(),
            log_level="warning",
            access_log=False,
        )
    finally:
        # Single release site (normal shutdown / uvicorn return); the SIGTERM
        # handler covers signalled termination.
        bootstrap.release()
        sock.close()


if __name__ == "__main__":
    main()
