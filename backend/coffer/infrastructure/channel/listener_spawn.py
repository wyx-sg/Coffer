"""Spawn/supervise the callback-listener child process.

Satisfies ``ListenerControllerPort``. The listener gets its signing secrets,
the daemon URL, and the daemon token via env at spawn (the established MCP
subprocess pattern — secrets land only in the child's env, never on disk).
The spawn goes through :class:`ChildProcess`, which records it in the
upstream-pids directory so a daemon crash leaves nothing behind: the startup
orphan sweep reaps it.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path

from coffer.infrastructure.daemon.child_process import ChildProcess

_logger = logging.getLogger(__name__)

_DEFAULT_PORT = 8787
_PIDFILE_PREFIX = "channel-callback"


def _listener_command() -> list[str]:
    """Resolve the child command for source installs and frozen builds."""
    if getattr(sys, "frozen", False):  # pragma: no cover - packaged builds only
        sibling = Path(sys.executable).with_name("coffer-callback")
        if sibling.exists():
            return [str(sibling)]
        raise RuntimeError(
            "frozen build is missing the coffer-callback sibling binary; "
            "SeaTalk channels need it for webhook ingress"
        )
    return [sys.executable, "-m", "coffer.surfaces.callback"]


class CallbackListenerController:
    """Owns at most one listener child for the whole daemon."""

    def __init__(
        self,
        *,
        daemon_info: Callable[[], tuple[str, str]],
        port: int | None = None,
    ) -> None:
        self._daemon_info = daemon_info
        self._port = (
            port
            if port is not None
            else int(os.environ.get("COFFER_CALLBACK_PORT", str(_DEFAULT_PORT)))
        )
        self._child: ChildProcess | None = None
        self._secrets: dict[str, str] = {}
        self._spawned_token: str | None = None

    @property
    def port(self) -> int:
        return self._port

    def running(self) -> bool:
        return self._child is not None and self._child.running

    async def ensure_running(self, signing_secrets: dict[str, str]) -> None:
        daemon_url, daemon_token = self._daemon_info()
        if (
            self.running()
            and signing_secrets == self._secrets
            # The token is baked into the child's env at spawn — a rotation
            # must respawn the listener or every forward starts failing 401.
            and daemon_token == self._spawned_token
        ):
            return
        await self.ensure_stopped()
        env = dict(os.environ)
        env.update(
            {
                "COFFER_CB_PORT": str(self._port),
                "COFFER_CB_SECRETS": json.dumps(signing_secrets),
                "COFFER_CB_DAEMON_URL": daemon_url,
                "COFFER_CB_DAEMON_TOKEN": daemon_token,
            }
        )
        command = _listener_command()
        self._child = await ChildProcess.spawn(_PIDFILE_PREFIX, command, env=env)
        self._secrets = dict(signing_secrets)
        self._spawned_token = daemon_token
        _logger.info("channel.listener.started", extra={"port": self._port, "pid": self._child.pid})

    async def ensure_stopped(self) -> None:
        child, self._child = self._child, None
        self._secrets = {}
        if child is None:
            return
        # terminate() also drops the pidfile once the child is reaped, so the
        # next startup sweep has nothing to chase — even if it had already exited.
        await child.terminate()
        _logger.info("channel.listener.stopped")
