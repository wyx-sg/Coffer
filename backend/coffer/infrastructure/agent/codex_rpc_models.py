"""``CodexRpcModelDiscovery`` — ask Codex itself which models it offers.

WHY this exists. Codex has no ``list models`` command either, but its
app-server protocol — the one Coffer already drives to run a turn — answers a
``model/list`` request. So the honest source for "what can Codex run today" is
Codex, asked at runtime. A list written into Coffer was not merely stale, it was
wrong: the names it carried did not exist on this machine at all.

WHAT this costs when it breaks. A Codex that is missing, broken, not logged in,
or simply slow yields nothing and the picker falls back to the other sources.
The probe is bounded by a timeout, the process is always torn down, and no
failure ever reaches the caller.

The subprocess transport is injected rather than imported so this module stays
free of the chat package (and so tests drive a scripted peer, never a real CLI).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import pathlib
import time
from collections.abc import Callable
from typing import Any, Protocol

from coffer.domain.agent.model_catalogue import AgentModel

_log = logging.getLogger(__name__)

#: The agent type this adapter knows how to interrogate.
_AGENT_KEY = "codex"

#: What Coffer calls itself in the app-server handshake.
_CLIENT_INFO = {"name": "coffer", "title": None, "version": "0"}

#: Pagination guard. ``model/list`` returns a cursor; a peer that kept handing
#: one back would otherwise spin forever.
_MAX_PAGES = 10


class _Rpc(Protocol):
    """The two calls this probe makes on the JSON-RPC client, structurally."""

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]: ...

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None: ...


class _Session(Protocol):
    """A started app-server process exposing its RPC client."""

    @property
    def rpc(self) -> _Rpc: ...

    async def start(self) -> None: ...

    async def close(self) -> None: ...


#: ``(cwd, env) -> session`` — satisfied by the chat package's production
#: factory, wired at the composition root.
SessionFactory = Callable[[str, dict[str, str] | None], _Session]


class CodexRpcModelDiscovery:
    """``ModelDiscoveryPort`` backed by Codex's own ``model/list`` RPC.

    Answers are held for ``ttl`` seconds per agent key: spawning a CLI is far
    too expensive to repeat per HTTP request, and the set of models a release
    offers does not change minute to minute.
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        timeout: float = 8.0,
        ttl: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._timeout = timeout
        self._ttl = ttl
        self._clock = clock
        self._cache: dict[str, tuple[float, list[AgentModel]]] = {}

    async def discover(
        self, *, agent_key: str, config_dir: pathlib.Path | None
    ) -> list[AgentModel]:
        if agent_key != _AGENT_KEY:
            return []
        cached = self._cache.get(agent_key)
        if cached is not None and self._clock() < cached[0]:
            return list(cached[1])
        models = await self._probe(config_dir)
        # Only a real answer is worth holding. An empty one means Codex was
        # missing, wedged or not logged in — all states the user fixes in
        # seconds, and caching them would leave the picker empty long after
        # they had. Re-probing costs a spawn we only pay while it is broken.
        if models:
            self._cache[agent_key] = (self._clock() + self._ttl, models)
        return list(models)

    # --- internals -----------------------------------------------------------

    async def _probe(self, config_dir: pathlib.Path | None) -> list[AgentModel]:
        """Spawn, handshake, list, tear down. Every failure is an empty list —
        including the timeout, whose whole job is to stop a wedged CLI from
        holding a model picker open."""
        cwd = self._cwd(config_dir)
        try:
            session = self._session_factory(cwd, None)
        except Exception:
            # Most often: the CLI is not installed at all.
            _log.debug("agent.model_discovery.codex_unavailable", exc_info=True)
            return []
        try:
            return await asyncio.wait_for(self._list(session), timeout=self._timeout)
        except TimeoutError:
            _log.debug("agent.model_discovery.codex_timeout")
            return []
        except Exception:
            _log.debug("agent.model_discovery.codex_failed", exc_info=True)
            return []
        finally:
            # The process must not outlive the probe even when the probe was
            # cancelled mid-handshake.
            with contextlib.suppress(Exception):
                await session.close()

    @staticmethod
    def _cwd(config_dir: pathlib.Path | None) -> str:
        """``model/list`` needs no project context, but the process still has to
        start somewhere that exists."""
        if config_dir is not None:
            with contextlib.suppress(OSError):
                if config_dir.is_dir():
                    return str(config_dir)
        return str(pathlib.Path.home())

    async def _list(self, session: _Session) -> list[AgentModel]:
        await session.start()
        rpc = session.rpc
        await rpc.request("initialize", {"clientInfo": _CLIENT_INFO, "capabilities": None})
        await rpc.notify("initialized")

        models: list[AgentModel] = []
        cursor: str | None = None
        for _ in range(_MAX_PAGES):
            params: dict[str, Any] = {} if cursor is None else {"cursor": cursor}
            result = await rpc.request("model/list", params)
            models.extend(self._page(result.get("data")))
            nxt = result.get("nextCursor")
            if not isinstance(nxt, str) or not nxt:
                break
            cursor = nxt
        return models

    @staticmethod
    def _page(data: Any) -> list[AgentModel]:
        if not isinstance(data, list):
            return []
        out: list[AgentModel] = []
        for entry in data:
            if not isinstance(entry, dict) or entry.get("hidden") is True:
                # ``hidden`` marks models the CLI itself will not show; offering
                # them in Coffer's picker would be offering a dead end.
                continue
            # ``id`` is the canonical field; ``model`` is what older releases
            # sent, and is what the CLI is ultimately configured with.
            ident = entry.get("id") or entry.get("model")
            if not isinstance(ident, str) or not ident.strip():
                continue
            label = entry.get("displayName")
            description = entry.get("description")
            out.append(
                AgentModel(
                    id=ident.strip(),
                    label=label.strip() if isinstance(label, str) else "",
                    description=description.strip() if isinstance(description, str) else "",
                )
            )
        return out


__all__ = ["CodexRpcModelDiscovery", "SessionFactory"]
