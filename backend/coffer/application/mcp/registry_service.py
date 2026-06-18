"""Search the official MCP Registry and normalize results (ADR-029).

Thin application service: calls the registry client port, maps each raw entry to
a ``RegistryServer`` (with an inferred, editable config draft), and caches search
results briefly (the registry is a preview API — a short cache cuts redundant
outbound calls without persisting anything). The clock is injectable for tests.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from coffer.application.mcp.ports import MCPRegistryClientPort
from coffer.domain.mcp.registry import RegistryServer, map_registry_entry

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 50
_CACHE_TTL_SECONDS = 60.0


class MCPRegistrySearchService:
    """Browse the official MCP Registry; returns normalized, installable drafts."""

    def __init__(
        self,
        client: MCPRegistryClientPort,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._client = client
        self._clock = clock or time.monotonic
        self._cache: dict[tuple[str, int], tuple[float, list[RegistryServer]]] = {}

    async def search(self, query: str, limit: int = _DEFAULT_LIMIT) -> list[RegistryServer]:
        q = (query or "").strip()
        limit = max(1, min(int(limit), _MAX_LIMIT))
        key = (q, limit)
        now = self._clock()
        cached = self._cache.get(key)
        if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
        raw = await self._client.fetch_servers(q, limit)
        servers = [
            mapped for mapped in (map_registry_entry(item) for item in raw) if mapped is not None
        ]
        self._cache[key] = (now, servers)
        return servers
