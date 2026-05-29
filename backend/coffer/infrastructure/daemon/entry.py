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
import time

import uvicorn

from coffer.infrastructure.daemon import bootstrap

_logger = logging.getLogger(__name__)


def _install_signal_handlers() -> None:
    def _term(_sig: int, _frame: object) -> None:
        bootstrap.release()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)


# CODE-015: there is an inherent TOCTOU window between port_alloc.allocate
# closing its probe socket and uvicorn binding. Retry-on-EADDRINUSE with
# exponential backoff papers over the rare race (another process snags the
# port between probe-close and bind) and gives a graceful "no free port"
# error if it persists.
_MAX_PORT_RETRIES = 3
_RETRY_BACKOFF_SECONDS = (0.0, 0.1, 0.4)


def main() -> None:
    _install_signal_handlers()
    last_error: Exception | None = None
    for attempt in range(_MAX_PORT_RETRIES):
        info = bootstrap.acquire()
        try:
            uvicorn.run(
                "coffer.main:app",
                host="127.0.0.1",
                port=info.port,
                log_level="warning",
                access_log=False,
            )
            return
        except OSError as exc:
            # EADDRINUSE is errno 48 on macOS, 98 on Linux. Match by string
            # name so we don't have to import errno + special-case platforms.
            is_addr_in_use = getattr(exc, "errno", None) in {48, 98}
            if not is_addr_in_use:
                raise
            last_error = exc
            _logger.warning(
                "daemon.port_in_use_retrying",
                extra={"port": info.port, "attempt": attempt + 1},
            )
            bootstrap.release()
            time.sleep(_RETRY_BACKOFF_SECONDS[attempt])
        finally:
            bootstrap.release()
    raise RuntimeError(f"daemon failed to bind after {_MAX_PORT_RETRIES} attempts: {last_error}")


if __name__ == "__main__":
    main()
