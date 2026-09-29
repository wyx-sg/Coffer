"""Read Codex's official subscription windows over ``codex app-server`` (ADR
usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

A short-lived app-server is started, sent the same ``initialize`` →
``initialized`` handshake the chat adapter sends, asked
``account/rateLimits/read`` — the generated, non-experimental method Codex's
own ``/status`` screen calls — and closed. The Codex process reads its own
login; Coffer never touches ``auth.json`` or calls a usage endpoint itself.

``None`` means there is nothing official to show: Codex is not installed, did
not start, or answered the request with an error (it is not signed in with a
ChatGPT plan — an API-key login has no subscription windows).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.infrastructure.chat.codex_app_server import (
    AppServerSessionFactory,
    CodexAppServerSession,
    default_app_server_session,
)
from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcError

_logger = logging.getLogger(__name__)

#: Client info announced in the handshake (the chat adapter's own).
_CLIENT_INFO = {"name": "coffer", "title": None, "version": "0"}

#: Resolves the environment the app-server runs under (``CODEX_HOME`` for an
#: agent with its own config dir), or nothing for the default.
EnvResolver = Callable[[], Awaitable[dict[str, str]]]


class AppServerRateLimitReader:
    """``CodexRateLimitReader`` over a fresh ``codex app-server`` per read."""

    def __init__(
        self,
        *,
        session_factory: AppServerSessionFactory = default_app_server_session,
        resolve_env: EnvResolver | None = None,
        cwd: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._factory = session_factory
        self._resolve_env = resolve_env
        # The app-server needs a working directory; nothing is read from it.
        self._cwd = cwd or tempfile.gettempdir()
        self._timeout = timeout

    async def read(self) -> dict[str, Any] | None:
        env = await self._env()
        try:
            session = self._factory(self._cwd, env)
        except RuntimeError:
            return None  # codex is not on PATH
        try:
            return await asyncio.wait_for(self._ask(session), timeout=self._timeout)
        except CodexRpcError as exc:
            _logger.info("codex_rate_limits.unavailable", extra={"reason": exc.rpc_message})
            return None
        except (TimeoutError, OSError, RuntimeError):
            _logger.warning("codex_rate_limits.read_failed", exc_info=True)
            return None
        finally:
            with contextlib.suppress(Exception):
                await session.close()

    async def _env(self) -> dict[str, str] | None:
        if self._resolve_env is None:
            return None
        overrides = await self._resolve_env()
        # create_subprocess_exec REPLACES the environment: merge, never swap.
        return {**os.environ, **overrides} if overrides else None

    @staticmethod
    async def _ask(session: CodexAppServerSession) -> dict[str, Any]:
        await session.start()
        rpc = session.rpc
        await rpc.request("initialize", {"clientInfo": _CLIENT_INFO, "capabilities": None})
        await rpc.notify("initialized")
        return await rpc.request("account/rateLimits/read", {})


__all__ = ["AppServerRateLimitReader"]
