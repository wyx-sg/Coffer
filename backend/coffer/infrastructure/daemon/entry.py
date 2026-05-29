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
    _install_signal_handlers()
    # CODE-041: acquire() binds the port and hands us the live socket; passing
    # its fd to uvicorn means there is no close-then-rebind window in which the
    # port (already published in daemon.json with the token) could be stolen.
    # That also removes the old EADDRINUSE retry loop entirely — we own the
    # socket, so uvicorn cannot fail to bind it.
    _info, sock = bootstrap.acquire()
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
