"""Shim bootstrap helpers — daemon detect-or-spawn + handshake plumbing.

Split out of ``main.py`` so that module stays focused on the ``_Bridge`` stdio↔
HTTP/SSE pump. These free functions cover everything the bridge needs *around*
a live connection: discovering (and if necessary spawning) the daemon, wiring
the shim's diagnostic log to a file, and stamping the launch cwd into the
``initialize`` handshake.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.daemon.spawn import spawn_detached_daemon
from coffer.infrastructure.daemon.version_skew import skew_warning
from coffer.surfaces.cli._client import discover

_logger = logging.getLogger("coffer.shim")
_SHIM_LOG_DIR = Path.home() / ".coffer" / "logs"
_DAEMON_BOOT_TIMEOUT = 10  # seconds

#: MCP-reserved extension key the daemon reads the launch cwd from.
_CWD_META_KEY = "coffer/cwd"
#: MCP-reserved extension key the daemon reads the shim's self-reported
#: ``--agent`` identity from (spec mcp-gateway FR-021, amended).
_AGENT_META_KEY = "coffer/agent"


def _inject_meta(envelope: dict[str, Any], agent: str | None = None) -> None:
    """Stamp the shim's launch cwd — and, when known, its ``--agent`` identity
    — into an ``initialize`` envelope's ``params._meta`` so the daemon can
    resolve the per-project memory scope and which resources are active for
    this agent. The agent key is omitted entirely when no name was given (an
    unnamed shim launch, or a client that hasn't been re-installed yet)."""
    params = envelope.get("params")
    if not isinstance(params, dict):
        params = {}
        envelope["params"] = params
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
        params["_meta"] = meta
    with contextlib.suppress(OSError):
        meta[_CWD_META_KEY] = os.getcwd()
    if agent:
        meta[_AGENT_META_KEY] = agent


def _setup_shim_log() -> None:
    """Send our diagnostic log to a file (NOT stdout — that's the MCP wire).

    One file per process start, because several shims run concurrently and a
    shared handler is not multiprocess-safe. That is also why they accumulate:
    2,137 of them (40 MB) had built up since June with nothing deleting any.
    The daemon's retention worker now ages them out; this end just stops
    writing a file for a run that produces no diagnostics, by deferring the
    open until the first record.
    """
    try:
        _SHIM_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = _SHIM_LOG_DIR / f"shim-{os.getpid()}-{int(time.time())}.log"
        handler = logging.FileHandler(log_path, delay=True)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)
    except OSError:
        # Failed to set up log file — continue without it
        pass


async def _wait_for_daemon(timeout: float) -> DaemonInfo | None:
    """Poll ~/.coffer/daemon.json until it appears + the daemon answers /status."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = discover()
        if info is not None:
            try:
                async with httpx.AsyncClient(
                    base_url=f"http://127.0.0.1:{info.port}/api/v1", timeout=2.0
                ) as c:
                    r = await c.get("/daemon/status")
                    if r.status_code == 200:
                        _warn_if_version_skew(r)
                        return info
            except Exception:
                pass
        await asyncio.sleep(0.2)
    return None


def _warn_if_version_skew(response: httpx.Response) -> None:
    """One line on stderr (and in the shim log) when the daemon that answered
    is a different build than this shim — a stale daemon from a previous
    install that detect-or-spawn quietly reused. Detection only: the MCP
    client keeps its session; the user restarts the daemon when they choose.
    """
    try:
        body = response.json()
    except ValueError:
        return
    message = skew_warning(body if isinstance(body, dict) else None, caller="coffer-mcp-shim")
    if message is not None:
        _logger.warning("shim.daemon_version_skew %s", message)
        sys.stderr.write(message + "\n")


def _spawn_daemon() -> None:
    """Best-effort detached spawn of the coffer-daemon binary.

    The shared :func:`spawn_detached_daemon` (ADR daemon-detect-or-spawn)
    picks the right binary whether the shim runs from source or as a frozen
    bundle beside ``coffer-daemon``, and sends the daemon's stdio to
    ``daemon.log`` — so a daemon that refuses to start (its fixed port is
    taken) leaves its reason where "check daemon.log" points, instead of the
    ``DEVNULL`` this used to pass that reduced every refusal to "did not come
    up within 10s".
    """
    try:
        spawn_detached_daemon()
    except OSError as e:
        _logger.exception("shim.spawn_daemon_failed")
        sys.stderr.write(f"coffer-mcp-shim: failed to spawn daemon: {e}\n")


async def _ensure_daemon() -> DaemonInfo:
    """Return a DaemonInfo for a reachable daemon, spawning one if needed."""
    info = await _wait_for_daemon(timeout=1.0)
    if info is not None:
        return info
    _spawn_daemon()
    info = await _wait_for_daemon(timeout=_DAEMON_BOOT_TIMEOUT)
    if info is None:
        sys.stderr.write(
            f"coffer-mcp-shim: daemon did not come up within {_DAEMON_BOOT_TIMEOUT}s; "
            "check ~/.coffer/logs/daemon.log\n"
        )
        sys.exit(3)
    return info
