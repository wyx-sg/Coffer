import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.application.retention_service import RetentionService
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyRetentionRepo,
)
from coffer.infrastructure.persistence.retention import (
    PrunableRegistry,
    PrunableTable,
)
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_retention_service
from coffer.surfaces.http.retention_routes import router as retention_router


async def _client(tmp_path, *extra_tables: PrunableTable):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    registry = PrunableRegistry()
    registry.register(
        PrunableTable(
            name="audit_log",
            timestamp_column="timestamp",
            default_retention_days=365,
            display_name="Audit Log",
            description="Resource lifecycle events.",
        )
    )
    for extra in extra_tables:
        registry.register(extra)
    repo = SqlAlchemyRetentionRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    svc = RetentionService(registry=registry, repo=repo, audit=audit)
    await svc.initialize_defaults()

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(retention_router)
    app.dependency_overrides[get_retention_service] = lambda: svc

    set_active_token("test-token")
    transport = ASGITransport(app)
    client = AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    )
    return client, engine


@pytest.mark.asyncio
async def test_list_policies(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.get("/api/v1/retention/policies")
        assert r.status_code == 200
        body = r.json()
        assert len(body["policies"]) == 1
        p = body["policies"][0]
        assert p["table_name"] == "audit_log"
        assert p["display_name"] == "Audit Log"
        assert p["default_retention_days"] == 365
        assert p["retention_days"] == 365
        assert p["last_pruned_rows"] == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_policy_days(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.patch(
            "/api/v1/retention/policies/audit_log",
            json={"retention_days": 90},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["retention_days"] == 90
        # Re-read via list
        r = await c.get("/api/v1/retention/policies")
        assert r.json()["policies"][0]["retention_days"] == 90
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_policy_forever(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.patch(
            "/api/v1/retention/policies/audit_log",
            json={"retention_days": None},
        )
        assert r.status_code == 200
        assert r.json()["retention_days"] is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_policy_unknown_table_404(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.patch(
            "/api/v1/retention/policies/nope",
            json={"retention_days": 30},
        )
        # UnknownPrunableTable -> 404 by default code mapping? Verify the
        # error envelope; the route surfaces the domain CofferError as 404.
        assert r.status_code in (400, 404)
        assert r.json()["error"]["code"] == "UNKNOWN_PRUNABLE_TABLE"
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_policy_rejects_zero(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.patch(
            "/api/v1/retention/policies/audit_log",
            json={"retention_days": 0},
        )
        # Pydantic ge=1 rejects 0 -> 422
        assert r.status_code == 422
    await engine.dispose()


@pytest.mark.asyncio
async def test_prune_all_tables(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.post("/api/v1/retention/prune", json={})
        assert r.status_code == 200
        body = r.json()
        assert "audit_log" in body["tables"]
        # Empty database — 0 rows pruned
        assert body["tables"]["audit_log"] == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_prune_single_table(tmp_path):
    """`table_name` must scope the prune to exactly that table. With TWO tables
    registered, pruning only audit_log must touch audit_log and NOT the other —
    otherwise the test can't distinguish single-table from prune-all."""
    second = PrunableTable(
        name="mcp_invocations",
        timestamp_column="timestamp",
        default_retention_days=30,
        display_name="MCP Invocations",
        description="MCP invocation log.",
    )
    c, engine = await _client(tmp_path, second)
    async with c:
        r = await c.post(
            "/api/v1/retention/prune",
            json={"table_name": "audit_log"},
        )
        assert r.status_code == 200
        tables = r.json()["tables"]
        assert "audit_log" in tables
        assert "mcp_invocations" not in tables, "table_name must scope prune to one table"

        # Sanity: prune-all DOES touch both, proving the second table is prunable.
        r_all = await c.post("/api/v1/retention/prune", json={})
        assert r_all.status_code == 200
        assert set(r_all.json()["tables"]) == {"audit_log", "mcp_invocations"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_prune_unknown_table(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.post(
            "/api/v1/retention/prune",
            json={"table_name": "nope"},
        )
        assert r.status_code in (400, 404)
        assert r.json()["error"]["code"] == "UNKNOWN_PRUNABLE_TABLE"
    await engine.dispose()
