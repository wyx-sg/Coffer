"""Recovery for upstreams that failed a session's tools/list (ADR budget-driven-tool-tiering).

A per-server discovery timeout leaves that server's tools out of the aggregate
list. The client caches ``tools/list``, and the correcting
``notifications/tools/list_changed`` can only come from the server that never
connected — so without this the tools stay gone for the whole session.

``DegradedTracker`` owns that repair: it remembers which servers failed,
retries them in the background on a widening delay, and on recovery
invalidates the discovery cache and tells the client to re-list. It is
deliberately bounded — the supervisor already owns sticky background recovery;
this exists only to un-stick the client's cached list.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.mcp.discovery import CapabilityDiscovery

SendDownstream = Callable[[dict[str, Any]], Awaitable[None]]

# Widening retry ladder, in seconds. Short enough that a slow cold spawn is
# repaired while the agent is still working, bounded so a genuinely dead
# upstream is left to the supervisor's own cooldown.
RETRY_DELAYS = (2.0, 8.0, 30.0)


class DegradedTracker:
    """Tracks and repairs servers missing from the last tools/list."""

    def __init__(
        self,
        discovery: CapabilityDiscovery,
        send_downstream: SendDownstream,
    ) -> None:
        self._discovery = discovery
        self._send_downstream = send_downstream
        self._servers: set[str] = set()
        self._task: asyncio.Task[None] | None = None

    @property
    def servers(self) -> set[str]:
        """Servers whose tools are missing from the last listing."""
        return set(self._servers)

    def record(self, failed_servers: list[str]) -> None:
        """Replace the degraded set and start a recovery pass if it is non-empty."""
        self._servers = set(failed_servers)
        if self._servers:
            self._schedule()

    def _schedule(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.ensure_future(self._retry_loop())

    async def _retry_loop(self) -> None:
        for delay in RETRY_DELAYS:
            await asyncio.sleep(delay)
            if not self._servers:
                return
            if await self.recover_now():
                return

    async def recover_now(self) -> bool:
        """Re-discover degraded servers once. True if any recovered.

        On recovery the cache slice is invalidated and the client is told to
        re-list — the step that actually puts the tools back in front of the
        agent mid-session.
        """
        recovered = False
        for server in sorted(self._servers):
            try:
                await self._discovery.list_tools(server)
            except Exception:
                continue
            self._discovery.invalidate(server, "tool")
            self._servers.discard(server)
            recovered = True
        if recovered:
            await self._send_downstream(
                {"method": "notifications/tools/list_changed", "params": {}}
            )
        return recovered

    async def dispose(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        self._servers.clear()


__all__ = ["RETRY_DELAYS", "DegradedTracker"]
