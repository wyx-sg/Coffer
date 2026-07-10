"""Contract tests for the resource scope REST endpoints (ADR-045, Task 7).

GET/PUT /api/v1/resources/{kind}/{name}/scope. Colocated under tests/contract
(not tests/integration/surfaces/http, where the base CRUD routes are covered)
because this is the wire-contract surface for scope specifically: response
shapes, the SCOPE_INVALID envelope code, and 404 semantics. Client/fixture
style mirrors tests/integration/surfaces/http/test_resource_routes.py (ASGI
transport against a real SQLite-backed ResourceService).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.memory.kind import make_memory_kind
from coffer.application.resource_service import ResourceService
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router


async def _client(tmp_path):
    """Wire a real app with the production mcp_server/memory/agent Kinds.

    mcp_server and memory are the two ends of the scope_axes spectrum
    (("machine", "agent") vs () — no scope support); agent is a lifecycle
    kind (generic_create_allowed=False) used to prove update_scope is NOT
    gated on that flag.
    """
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    kinds = {
        "mcp_server": make_mcp_kind({}),
        "memory": make_memory_kind(None),  # type: ignore[arg-type]
        "agent": make_agent_kind(None),
    }
    repo = SqlAlchemyResourceRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    svc = ResourceService(kinds=kinds, repo=repo, audit=audit)

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(resource_router)
    app.dependency_overrides[get_resource_service] = lambda: svc

    set_active_token("test-token")
    transport = ASGITransport(app)
    client = AsyncClient(
        transport=transport, base_url="http://t", headers={"X-Coffer-Token": "test-token"}
    )
    return client, engine, svc


@pytest.mark.asyncio
async def test_get_scope_returns_null_and_axes_for_mcp_server(tmp_path):
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(
            kind="mcp_server",
            name="fs",
            config={"transport": {"type": "http", "url": "http://example.com/mcp"}},
            actor="cli",
        )
        r = await c.get("/api/v1/resources/mcp_server/fs/scope")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["scope"] is None
        assert sorted(body["axes"]) == ["agent", "machine"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_round_trips_matrix_and_response_carries_scope(tmp_path):
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(
            kind="mcp_server",
            name="fs",
            config={"transport": {"type": "http", "url": "http://example.com/mcp"}},
            actor="cli",
        )
        matrix = {"machine-1": ["agent-a", "agent-b"], "machine-2": "*"}
        r = await c.put("/api/v1/resources/mcp_server/fs/scope", json={"scope": matrix})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["scope"] == matrix
        assert body["ref"] == "mcp_server:fs"

        # Round-trip through GET too.
        get_r = await c.get("/api/v1/resources/mcp_server/fs/scope")
        assert get_r.status_code == 200
        assert get_r.json()["scope"] == matrix

        # Full ResourceOut GET also carries scope.
        full_r = await c.get("/api/v1/resources/mcp_server/fs")
        assert full_r.status_code == 200
        assert full_r.json()["scope"] == matrix
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_on_memory_kind_returns_422_scope_invalid(tmp_path):
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(kind="memory", name="notes", config={}, actor="cli")
        r = await c.put(
            "/api/v1/resources/memory/notes/scope",
            json={"scope": {"machine-1": "*"}},
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "SCOPE_INVALID"
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_unknown_name_returns_404(tmp_path):
    c, engine, _svc = await _client(tmp_path)
    async with c:
        r = await c.put(
            "/api/v1/resources/mcp_server/nope/scope",
            json={"scope": {"machine-1": "*"}},
        )
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_works_for_lifecycle_kind_agent(tmp_path):
    """update_scope is framework-level and must not be gated on
    generic_create_allowed — an agent (a lifecycle kind whose creation is
    owned by AgentService, not the generic POST /resources path) must still
    accept scope writes through the dedicated PUT .../scope route."""
    c, engine, svc = await _client(tmp_path)
    async with c:
        # Seed directly (agent's real creation flow is owned by AgentService,
        # not exercised here) — allow_lifecycle_kind mirrors that dedicated
        # service opting in, per CODE-REG.
        await svc.register(
            kind="agent",
            name="claude",
            config={"type": "claude_code"},
            actor="agent-service",
            allow_lifecycle_kind=True,
        )
        r = await c.put(
            "/api/v1/resources/agent/claude/scope",
            json={"scope": {"machine-1": "*"}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["scope"] == {"machine-1": "*"}
    await engine.dispose()
