"""Shim bootstrap helpers — daemon detect-or-spawn + handshake plumbing.

Split out of ``main.py`` so that module stays focused on the ``_Bridge`` stdio↔
HTTP/SSE pump. These free functions cover everything the bridge needs *around*
a live connection: parsing the shim's own launch flags, discovering (and if
necessary spawning) the daemon, wiring the shim's diagnostic log to a file, and
stamping the launch cwd and the agent identity into the ``initialize``
handshake. The flag and the ``_meta`` key it turns into live next to each other
here on purpose — they are two halves of one fact and drifted apart once.
"""

from __future__ import annotations

import argparse
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
#: MCP-reserved extension key the daemon reads the shim's self-reported agent
#: identity from (spec mcp-gateway "Take the agent identity from the
#: handshake"). The value is the agent
#: resource's **uid**, which is why the key is not the older ``coffer/agent``:
#: that one carried a name, the gateway no longer reads it, and giving the same
#: key a new meaning would leave an old shim's stale name being matched against
#: a scope that now holds uids (ADR resource-identity-is-an-immutable-uid).
_AGENT_UID_META_KEY = "coffer/agent-uid"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the shim's own CLI args — the self-reported agent identity.

    ``--agent-uid <uid>`` is what Coffer writes into an agent's native MCP config
    (``domain.agent.mcp_install``). It carries the agent resource's **uid**
    because this string outlives the edit that renames the agent — the entry is
    written once into a file Coffer does not otherwise touch — and because the
    gateway matches what we report against the uids a resource's ``scope`` holds
    (ADR resource-identity-is-an-immutable-uid).

    The name-shaped ``--agent`` that preceded it is NOT accepted, and
    ``allow_abbrev=False`` is what makes that true rather than merely tidy:
    argparse takes any unambiguous PREFIX of a long option, and ``--agent`` is a
    prefix of ``--agent-uid``. Left on, every entry an older Coffer wrote would
    report the agent's NAME as its uid, and the gateway would compare that label
    against a list of uids — the silent mismatch this change exists to remove.
    Discarded instead, such a shim reports nothing and its session is
    unidentified: strictly less access, never more, and re-installing fixes it.

    The shim is spawned by an MCP client's server-launch config, which may
    already pass other flags we don't know about — ``parse_known_args`` and
    discarding the rest keeps the shim maximally compatible rather than
    crashing on an unrecognized flag.
    """
    parser = argparse.ArgumentParser(prog="coffer-mcp-shim", add_help=False, allow_abbrev=False)
    parser.add_argument("--agent-uid", dest="agent_uid", default=None)
    namespace, _unknown = parser.parse_known_args(argv)
    return namespace


def _inject_meta(envelope: dict[str, Any], agent_uid: str | None = None) -> None:
    """Stamp the shim's launch cwd — and, when known, its ``--agent-uid``
    identity — into an ``initialize`` envelope's ``params._meta`` so the daemon
    can resolve the per-project memory scope and which resources are active for
    this agent. The agent key is omitted entirely when no uid was given (a
    hand-configured shim, or a client whose entry Coffer has not written)."""
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
    if agent_uid:
        meta[_AGENT_UID_META_KEY] = agent_uid


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
