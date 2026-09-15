"""Spawn/supervise per-channel cloudflared named-tunnel child processes.

Satisfies ``TunnelControllerPort``. When a SeaTalk channel records a Cloudflare
connector token, the daemon keeps a ``cloudflared tunnel run`` child alive for
it so the channel's public callback URL is reachable without the user running a
tunnel by hand. One child per channel (each named tunnel has its own token).

The token never lands in argv (``ps`` is world-readable) — it is written to a
0600 temp file and passed with ``--token-file``, removed on stop. Each spawn goes
through :class:`ChildProcess`, which records it in the upstream-pids directory
so a daemon crash leaves nothing behind: the startup orphan sweep reaps it.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from coffer.infrastructure.daemon.child_process import ChildProcess

_logger = logging.getLogger(__name__)

_PIDFILE_PREFIX = "channel-tunnel"
# cloudflared is often installed by a package manager into a dir that GUI-spawned
# daemons don't have on PATH; probe the common ones as a fallback.
_FALLBACK_BINDIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")


class CloudflaredNotFoundError(RuntimeError):
    """cloudflared is not installed / not resolvable."""


def _resolve_cloudflared() -> str:
    found = shutil.which("cloudflared")
    if found:
        return found
    for d in _FALLBACK_BINDIRS:
        candidate = Path(d) / "cloudflared"
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise CloudflaredNotFoundError(
        "cloudflared is not installed; install it (e.g. `brew install cloudflared`) "
        "to let Coffer manage the SeaTalk tunnel"
    )


@dataclass
class _Tunnel:
    child: ChildProcess
    token: str
    token_file: Path


class TunnelController:
    """Owns one cloudflared child per managed channel."""

    def __init__(self) -> None:
        self._tunnels: dict[str, _Tunnel] = {}

    def running(self, name: str) -> bool:
        t = self._tunnels.get(name)
        return t is not None and t.child.running

    def active(self) -> set[str]:
        return {name for name in self._tunnels if self.running(name)}

    async def ensure_running(self, name: str, token: str) -> None:
        existing = self._tunnels.get(name)
        if existing is not None and existing.child.running and existing.token == token:
            return
        await self.ensure_stopped(name)
        binary = (
            _resolve_cloudflared()
        )  # raises CloudflaredNotFoundError — caught by the reconciler
        fd, path_str = tempfile.mkstemp(prefix=f"coffer-tunnel-{name}-", suffix=".token")
        token_file = Path(path_str)
        with os.fdopen(fd, "w") as f:
            f.write(token)
        token_file.chmod(0o600)
        command = [
            binary,
            "tunnel",
            "--no-autoupdate",
            "run",
            "--token-file",
            str(token_file),
            "--protocol",
            "http2",
        ]
        child = await ChildProcess.spawn(_PIDFILE_PREFIX, command)
        self._tunnels[name] = _Tunnel(child=child, token=token, token_file=token_file)
        _logger.info("channel.tunnel.started", extra={"channel": name, "pid": child.pid})

    async def ensure_stopped(self, name: str) -> None:
        tunnel = self._tunnels.pop(name, None)
        if tunnel is None:
            return
        await tunnel.child.terminate()
        with contextlib.suppress(Exception):
            tunnel.token_file.unlink(missing_ok=True)
        _logger.info("channel.tunnel.stopped", extra={"channel": name})

    async def dispose(self) -> None:
        for name in list(self._tunnels):
            await self.ensure_stopped(name)
