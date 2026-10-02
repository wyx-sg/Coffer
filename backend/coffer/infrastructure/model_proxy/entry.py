"""Model proxy entry — ``coffer-daemon proxy [--port N]`` in a frozen build,
``python -m coffer.infrastructure.model_proxy.entry [--port N]`` from source.

One binary, two modes (ADR api-key-providers-are-reached-through-a-separate-
local-model-proxy, "Distribution"): the daemon's own entry hands ``proxy`` off
to :func:`main` before it does anything else, so no fourth binary is built.

Start-up order matters for the supervisor that is waiting on us:

1. bind ``127.0.0.1:<port>`` — loopback only, with no option for another
   interface — and refuse to start if the port is held (a fixed port that
   quietly became another port would disconnect every agent config);
2. write ``proxy.json`` with a fresh control token, only once the socket is
   ours, so a reader never finds a file naming a port we do not hold;
3. serve on the pre-bound socket (uvicorn ``fd=``, so there is no
   close-then-rebind gap).

On exit — SIGTERM, a drain that reached zero in-flight requests, or a crash
out of uvicorn — ``proxy.json`` is removed only if it still names this pid.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import secrets
import signal
import sys
from collections.abc import Iterator, Sequence

import uvicorn

from coffer.infrastructure.daemon.config import effective_proxy_port
from coffer.infrastructure.daemon.port_alloc import PortInUse, bind_fixed_socket
from coffer.infrastructure.model_proxy.app import ModelProxyApp, now_iso
from coffer.infrastructure.model_proxy.info import (
    EXIT_PORT_IN_USE,
    ProxyInfo,
    remove_info_if_owned,
    write_info,
)
from coffer.infrastructure.model_proxy.spool import UsageSpool

_logger = logging.getLogger(__name__)

#: How long SIGTERM waits for open streams before closing them. A drain (the
#: upgrade path) waits for zero in-flight requests instead; this bound is for
#: logout and ``kill``, where the process must actually go.
SHUTDOWN_GRACE_SECONDS = 30


class _ProxyServer(uvicorn.Server):
    """uvicorn, minus its habit of re-raising a caught SIGTERM after shutdown.

    uvicorn turns SIGINT/SIGTERM into a graceful ``should_exit`` and then, once
    serving has stopped, raises the signal again so the process dies of it —
    which would skip the cleanup below (``proxy.json`` would outlive us, naming
    a dead pid). Here a signal only asks for the graceful exit, and the process
    ends normally with status 0.
    """

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        def _exit(_sig: int, _frame: object) -> None:
            self.should_exit = True

        previous = {sig: signal.signal(sig, _exit) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            yield
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def _version() -> str:
    try:
        from coffer import __version__

        return __version__
    except Exception:  # an unpackaged source tree has no distribution metadata
        return "0+unknown"


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="coffer-daemon proxy", description=__doc__)
    parser.add_argument("--port", type=int, default=None, help="loopback port to bind")
    return parser.parse_args(list(argv) if argv is not None else None)


def _configure_logging() -> None:
    """Metadata-only lines to stderr, which the supervisor points at proxy.log."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # httpx logs every request URL at INFO; the URLs carry no secret, but the
    # line per model call is noise the usage record already covers.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse(argv)
    _configure_logging()
    port = args.port if args.port is not None else effective_proxy_port()
    try:
        sock = bind_fixed_socket(port)
    except PortInUse:
        print(
            f"Coffer's model proxy could not bind 127.0.0.1:{port}: the port is in use.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_PORT_IN_USE) from None
    pid = os.getpid()
    version = _version()
    started_at = now_iso()
    info = ProxyInfo(
        port=port,
        pid=pid,
        started_at=started_at,
        version=version,
        control_token=secrets.token_urlsafe(32),
    )
    server: _ProxyServer | None = None

    def _drained() -> None:
        _logger.info("model_proxy.drained; exiting")
        if server is not None:
            server.should_exit = True

    app = ModelProxyApp(
        control_token=info.control_token,
        version=version,
        started_at=started_at,
        spool=UsageSpool(),
        on_drained=_drained,
    )
    config = uvicorn.Config(
        app,
        fd=sock.fileno(),
        lifespan="on",
        log_level="warning",
        access_log=False,
        timeout_graceful_shutdown=SHUTDOWN_GRACE_SECONDS,
    )
    server = _ProxyServer(config)
    try:
        write_info(info)
        _logger.info("model_proxy.started pid=%s port=%s version=%s", pid, port, version)
        asyncio.run(server.serve())
    finally:
        remove_info_if_owned(pid)
        sock.close()
        _logger.info("model_proxy.stopped pid=%s", pid)


if __name__ == "__main__":
    main()
