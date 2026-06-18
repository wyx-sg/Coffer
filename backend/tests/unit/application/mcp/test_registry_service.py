"""Unit tests for MCPRegistrySearchService — mapping, caching, clamping (ADR-029)."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.mcp.registry_service import MCPRegistrySearchService

_NPM = {
    "server": {
        "name": "com.example/fs",
        "description": "files",
        "packages": [
            {"registryType": "npm", "identifier": "fs-mcp", "transport": {"type": "stdio"}}
        ],
    }
}


class _FakeClient:
    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self.entries = entries
        self.calls: list[tuple[str, int]] = []

    async def fetch_servers(self, query: str, limit: int) -> list[dict[str, Any]]:
        self.calls.append((query, limit))
        return self.entries


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@pytest.mark.asyncio
async def test_search_maps_entries_to_installable_servers() -> None:
    svc = MCPRegistrySearchService(_FakeClient([_NPM]))
    out = await svc.search("fs", 10)
    assert len(out) == 1
    assert out[0].name == "com.example/fs"
    assert out[0].installable is True
    assert out[0].draft is not None and out[0].draft.command == "npx"


@pytest.mark.asyncio
async def test_results_are_cached_within_ttl_then_refetched() -> None:
    clock = _Clock()
    client = _FakeClient([_NPM])
    svc = MCPRegistrySearchService(client, clock=clock)

    await svc.search("fs", 10)
    await svc.search("fs", 10)  # within TTL → served from cache
    assert client.calls == [("fs", 10)]

    clock.t = 61.0  # past the 60s TTL
    await svc.search("fs", 10)
    assert len(client.calls) == 2  # cache expired → upstream hit again


@pytest.mark.asyncio
async def test_limit_is_clamped_to_1_50() -> None:
    client = _FakeClient([])
    svc = MCPRegistrySearchService(client)
    await svc.search("x", 999)
    await svc.search("x", 0)
    assert client.calls[0][1] == 50
    assert client.calls[1][1] == 1


@pytest.mark.asyncio
async def test_query_is_trimmed() -> None:
    client = _FakeClient([])
    svc = MCPRegistrySearchService(client)
    await svc.search("  fs  ", 5)
    assert client.calls[0][0] == "fs"


@pytest.mark.asyncio
async def test_cache_key_includes_limit() -> None:
    client = _FakeClient([_NPM])
    svc = MCPRegistrySearchService(client)
    await svc.search("fs", 10)
    await svc.search("fs", 20)  # different limit → distinct cache key, not a hit
    assert client.calls == [("fs", 10), ("fs", 20)]
