"""Integration tests for GET /api/v1/mcp-registry/search (ADR-029).

Drives the route through the ASGI app with a stub registry client, so the full
HTTP path (validation, mapping, error envelope) is exercised end-to-end.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.mcp.registry_service import MCPRegistrySearchService
from coffer.domain.mcp.registry import RegistryUnavailable
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.mcp.registry_dependencies import set_mcp_registry_service
from coffer.surfaces.http.mcp.registry_routes import router as registry_router

_NPM_ENTRY = {
    "server": {
        "name": "com.example/fs",
        "description": "filesystem server",
        "version": "1.0.0",
        "packages": [
            {
                "registryType": "npm",
                "identifier": "fs-mcp",
                "version": "1.0.0",
                "transport": {"type": "stdio"},
                "environmentVariables": [{"name": "TOKEN", "isSecret": True, "isRequired": True}],
            }
        ],
    }
}


class _StubClient:
    def __init__(
        self, entries: list[dict[str, Any]], *, raise_exc: Exception | None = None
    ) -> None:
        self._entries = entries
        self._raise = raise_exc

    async def fetch_servers(self, query: str, limit: int) -> list[dict[str, Any]]:
        if self._raise is not None:
            raise self._raise
        return self._entries


def _client_for(service: MCPRegistrySearchService) -> AsyncClient:
    set_mcp_registry_service(service)
    set_active_token("test-token")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(registry_router)
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Coffer-Token": "test-token"},
    )


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="search the official MCP registry")
@pytest.mark.asyncio
async def test_search_returns_servers_with_installable_draft() -> None:
    svc = MCPRegistrySearchService(_StubClient([_NPM_ENTRY]))
    async with _client_for(svc) as client:
        r = await client.get("/api/v1/mcp-registry/search", params={"q": "fs"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["servers"]) == 1
    server = body["servers"][0]
    assert server["name"] == "com.example/fs"
    assert server["installable"] is True
    assert server["registry_type"] == "npm"
    assert server["draft"]["command"] == "npx"
    assert server["draft"]["args"][-1] == "fs-mcp@1.0.0"
    assert server["draft"]["env"] == [
        {"key": "TOKEN", "is_secret": True, "required": True, "description": None}
    ]


@pytest.mark.asyncio
async def test_missing_query_is_rejected_422() -> None:
    svc = MCPRegistrySearchService(_StubClient([]))
    async with _client_for(svc) as client:
        r = await client.get("/api/v1/mcp-registry/search")
    assert r.status_code == 422


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="registry search degrades when the registry is unavailable"
)
@pytest.mark.asyncio
async def test_registry_unavailable_returns_502() -> None:
    svc = MCPRegistrySearchService(_StubClient([], raise_exc=RegistryUnavailable("boom")))
    async with _client_for(svc) as client:
        r = await client.get("/api/v1/mcp-registry/search", params={"q": "fs"})
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "REGISTRY_UNAVAILABLE"
