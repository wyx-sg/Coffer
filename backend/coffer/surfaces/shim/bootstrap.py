"""Shim bootstrap helpers — daemon detect-or-spawn (ADR-006) + handshake plumbing.

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
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.daemon.spawn import daemon_spawn_command
from coffer.surfaces.cli._client import discover

_logger = logging.getLogger("coffer.shim")
_SHIM_LOG_DIR = Path.home() / ".coffer" / "logs"
_DAEMON_BOOT_TIMEOUT = 10  # seconds

#: MCP-reserved extension key the daemon reads the launch cwd from.
_CWD_META_KEY = "coffer/cwd"
#: MCP-reserved extension key the daemon reads the shim's self-reported
#: ``--agent`` identity from (spec 001 FR-021, amended).
_AGENT_META_KEY = "coffer/agent"


def _inject_meta(envelope: dict[str, Any], agent: str | None = None) -> None:
    """Stamp the shim's launch cwd — and, when known, its ``--agent`` identity
    — into an ``initialize`` envelope's ``params._meta`` so the daemon can
    resolve the per-project memory scope and the agent axis of resource
    scoping. The agent key is omitted entirely when no name was given (an
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


def _inject_cwd(envelope: dict[str, Any]) -> None:
    """Back-compat alias for :func:`_inject_meta` — stamps only the launch
    cwd. Kept for any call site that only cares about cwd propagation."""
    _inject_meta(envelope)


def _setup_shim_log() -> None:
    """Send our diagnostic log to a file (NOT stdout — that's the MCP wire)."""
    try:
        _SHIM_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = _SHIM_LOG_DIR / f"shim-{os.getpid()}-{int(time.time())}.log"
        handler = logging.FileHandler(log_path)
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
                        return info
            except Exception:
                pass
        await asyncio.sleep(0.2)
    return None


def _spawn_daemon() -> None:
    """Best-effort detached spawn of the coffer-daemon binary.

    Uses ``daemon_spawn_command()`` (ADR-006) so the correct binary is chosen
    whether the shim is running from source (dev/pip) or as a frozen
    PyInstaller bundle co-located with ``coffer-daemon``.
    """
    cmd = daemon_spawn_command()
    try:
        kwargs: dict[str, object] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            )
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)  # type: ignore[call-overload]
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
            f"coffer-mcp-shim: daemon did not come up within {_DAEMON_BOOT_TIMEOUT}s\n"
        )
        sys.exit(3)
    return info
