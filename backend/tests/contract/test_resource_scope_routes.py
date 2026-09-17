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
from coffer.application.knowledge.service import KIND_KNOWLEDGE
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.resource_service import ResourceService
from coffer.application.skill.kind import make_skill_kind
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

    Four real kinds, chosen so the two flags vary independently — because
    `supports_scope` and `generic_create_allowed` answer unrelated questions
    and the route must not confuse them. `mcp_server` and `agent` are the two
    ends of the scope spectrum among generically-creatable kinds; `skill` is a
    lifecycle kind (`generic_create_allowed=False`) that DOES support scope,
    proving update_scope is not gated on that flag, and `knowledge` is a
    lifecycle kind that supports NONE, proving the refusal is not either.
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
        await svc.register(
            kind="agent",
            name="claude",
            config={"type": "claude_code"},
            actor="agent-service",
            allow_lifecycle_kind=True,
        )
        r = await c.get("/api/v1/resources/agent/claude/scope")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["scope"] is None
        assert body["supports_scope"] is False
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="set a resource's reach from the kind-agnostic surface",
)
async def test_put_scope_round_trips_agent_list_and_response_carries_scope(tmp_path):
    """The agent allow-list rides the wire as one object."""
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(
            kind="mcp_server",
            name="fs",
            config={"transport": {"type": "http", "url": "http://example.com/mcp"}},
            actor="cli",
        )
        scope = {"agents": ["claude-code", "codex"]}
        r = await c.put("/api/v1/resources/mcp_server/fs/scope", json={"scope": scope})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["scope"] == scope
        assert body["ref"] == "mcp_server:fs"

        # Round-trip through GET too.
        get_r = await c.get("/api/v1/resources/mcp_server/fs/scope")
        assert get_r.status_code == 200
        assert get_r.json()["scope"] == scope

        # Full ResourceOut GET also carries scope.
        full_r = await c.get("/api/v1/resources/mcp_server/fs")
        assert full_r.status_code == 200
        assert full_r.json()["scope"] == scope
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_empty_scope_is_dormant_and_null_clears(tmp_path):
    """The three states stay distinct on the wire: an empty list is dormant, a
    null list is unrestricted, and a null scope clears the scope entirely."""
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(
            kind="mcp_server",
            name="fs",
            config={"transport": {"type": "http", "url": "http://example.com/mcp"}},
            actor="cli",
        )
        dormant = {"agents": []}
        r = await c.put("/api/v1/resources/mcp_server/fs/scope", json={"scope": dormant})
        assert r.status_code == 200, r.text
        assert r.json()["scope"] == dormant

        # A null list is unrestricted, which is not the same as no scope at all.
        unrestricted = {"agents": None}
        r_u = await c.put("/api/v1/resources/mcp_server/fs/scope", json={"scope": unrestricted})
        assert r_u.status_code == 200, r_u.text
        assert r_u.json()["scope"] == unrestricted

        r2 = await c.put("/api/v1/resources/mcp_server/fs/scope", json={"scope": None})
        assert r2.status_code == 200, r2.text
        assert r2.json()["scope"] is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_scope_on_a_lifecycle_kind_that_declares_none_is_reported_and_refused(tmp_path):
    """`knowledge` withdrew from reach, and the route must say so on both verbs.

    A collection is still a Resource, but for its lifecycle and its audit trail
    rather than for authorization: reach over a collection was non-disclosure
    only — the corpus is files on disk and the delivered skill tells the agent
    to grep the whole root — so the kind stopped declaring it. The refusal has
    to come from `supports_scope` alone and not from the kind being a lifecycle
    kind, which is why this is asserted on `knowledge` as well as on `agent`.
    """
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(
            kind=KIND_KNOWLEDGE,
            name="shopee",
            config={},
            actor="cli",
            allow_lifecycle_kind=True,
        )
        get_r = await c.get(f"/api/v1/resources/{KIND_KNOWLEDGE}/shopee/scope")
        assert get_r.status_code == 200, get_r.text
        assert get_r.json() == {"scope": None, "supports_scope": False}

        r = await c.put(
            f"/api/v1/resources/{KIND_KNOWLEDGE}/shopee/scope",
            json={"scope": {"agents": ["claude-code"]}},
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "SCOPE_INVALID"
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="set a resource's reach from the kind-agnostic surface",
)
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
            json={"scope": {"agents": ["claude-code"]}},
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "SCOPE_INVALID"
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_rejects_a_malformed_payload(tmp_path):
    c, engine, svc = await _client(tmp_path)
    async with c:
        await svc.register(
            kind="mcp_server",
            name="fs",
            config={"transport": {"type": "http", "url": "http://example.com/mcp"}},
            actor="cli",
        )
        # The pre-two-axis shape: a bare list is no longer a scope.
        r = await c.put(
            "/api/v1/resources/mcp_server/fs/scope",
            json={"scope": ["claude-code"]},
        )
        assert r.status_code == 422, r.text
        # An axis that is not a list of names is refused too.
        r2 = await c.put(
            "/api/v1/resources/mcp_server/fs/scope",
            json={"scope": {"agents": "claude-code"}},
        )
        assert r2.status_code == 422, r2.text
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_scope_unknown_name_returns_404(tmp_path):
    c, engine, _svc = await _client(tmp_path)
    async with c:
        r = await c.put(
            "/api/v1/resources/mcp_server/nope/scope",
            json={"scope": {"agents": ["claude-code"]}},
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
            json={"scope": {"agents": ["claude-code"]}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["scope"] == {"agents": ["claude-code"]}
    await engine.dispose()
