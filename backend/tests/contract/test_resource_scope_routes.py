"""Contract tests for the resource scope REST endpoints (ADR per-agent-resource-scope).

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
from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.resource_service import ResourceService
from coffer.application.skill.kind import make_skill_kind
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
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
    """Wire a real app with the production mcp_server/knowledge/agent/skill Kinds.

    mcp_server and knowledge are the two ends of the spectrum (supports_scope
    True vs False); skill is a lifecycle kind (generic_create_allowed=False)
    that DOES support scope, proving update_scope is not gated on that flag;
    agent is a lifecycle kind that does NOT.
    """
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    kinds = {
        "mcp_server": make_mcp_kind({}),
        KIND_KNOWLEDGE: make_knowledge_kind(None),  # type: ignore[arg-type]
        "agent": make_agent_kind(None),
        "skill": make_skill_kind(None),  # type: ignore[arg-type]
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
async def test_get_scope_returns_null_and_supports_scope_for_mcp_server(tmp_path):
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
        assert body["supports_scope"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_scope_reports_kinds_without_scope(tmp_path):
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(kind=KIND_KNOWLEDGE, name="notes", config={}, actor="cli")
        r = await c.get(f"/api/v1/resources/{KIND_KNOWLEDGE}/notes/scope")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["scope"] is None
        assert body["supports_scope"] is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_round_trips_agent_list_and_response_carries_scope(tmp_path):
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(
            kind="mcp_server",
            name="fs",
            config={"transport": {"type": "http", "url": "http://example.com/mcp"}},
            actor="cli",
        )
        agents = ["claude-code", "codex"]
        r = await c.put("/api/v1/resources/mcp_server/fs/scope", json={"scope": agents})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["scope"] == agents
        assert body["ref"] == "mcp_server:fs"

        # Round-trip through GET too.
        get_r = await c.get("/api/v1/resources/mcp_server/fs/scope")
        assert get_r.status_code == 200
        assert get_r.json()["scope"] == agents

        # Full ResourceOut GET also carries scope.
        full_r = await c.get("/api/v1/resources/mcp_server/fs")
        assert full_r.status_code == 200
        assert full_r.json()["scope"] == agents
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_empty_scope_is_dormant_and_null_clears(tmp_path):
    """The three states are distinct on the wire: [] (dormant) is persisted
    as an empty list, null clears back to unscoped."""
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(
            kind="mcp_server",
            name="fs",
            config={"transport": {"type": "http", "url": "http://example.com/mcp"}},
            actor="cli",
        )
        r = await c.put("/api/v1/resources/mcp_server/fs/scope", json={"scope": []})
        assert r.status_code == 200, r.text
        assert r.json()["scope"] == []

        r2 = await c.put("/api/v1/resources/mcp_server/fs/scope", json={"scope": None})
        assert r2.status_code == 200, r2.text
        assert r2.json()["scope"] is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_on_knowledge_kind_returns_422_scope_invalid(tmp_path):
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(kind=KIND_KNOWLEDGE, name="notes", config={}, actor="cli")
        r = await c.put(
            f"/api/v1/resources/{KIND_KNOWLEDGE}/notes/scope",
            json={"scope": ["claude-code"]},
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "SCOPE_INVALID"
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_on_agent_kind_returns_422_scope_invalid(tmp_path):
    """The `agent` kind declares no scope: scope names the agents a resource
    is active for, so an agent scoping itself is meaningless."""
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(
            kind="agent",
            name="claude",
            config={"type": "claude_code"},
            actor="agent-service",
            allow_lifecycle_kind=True,
        )
        r = await c.put(
            "/api/v1/resources/agent/claude/scope",
            json={"scope": ["claude-code"]},
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "SCOPE_INVALID"
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_rejects_a_non_list_payload(tmp_path):
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(
            kind="mcp_server",
            name="fs",
            config={"transport": {"type": "http", "url": "http://example.com/mcp"}},
            actor="cli",
        )
        r = await c.put(
            "/api/v1/resources/mcp_server/fs/scope",
            json={"scope": {"machine-1": "*"}},
        )
        assert r.status_code == 422, r.text
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_unknown_name_returns_404(tmp_path):
    c, engine, _svc = await _client(tmp_path)
    async with c:
        r = await c.put(
            "/api/v1/resources/mcp_server/nope/scope",
            json={"scope": ["claude-code"]},
        )
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_works_for_lifecycle_kind_skill(tmp_path):
    """update_scope is framework-level and must not be gated on
    generic_create_allowed — a skill (a lifecycle kind whose creation is
    owned by SkillService, not the generic POST /resources path) must still
    accept scope writes through the dedicated PUT .../scope route."""
    c, engine, svc = await _client(tmp_path)
    async with c:
        # Seed directly (a skill's real creation flow is owned by SkillService,
        # not exercised here) — allow_lifecycle_kind mirrors that dedicated
        # service opting in, per CODE-REG.
        await svc.register(
            kind="skill",
            name="reviewer",
            config={
                "source": {"type": "local_import", "original_path": "/tmp/reviewer"},
                "skill_md_name": "reviewer",
                "skill_md_description": "reviews things",
                "version_hash": "abc123",
            },
            actor="skill-service",
            allow_lifecycle_kind=True,
        )
        r = await c.put(
            "/api/v1/resources/skill/reviewer/scope",
            json={"scope": ["claude-code"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["scope"] == ["claude-code"]
    await engine.dispose()
