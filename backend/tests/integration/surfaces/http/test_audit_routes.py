from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.audit_routes import router as audit_router
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_audit_service


async def _client(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(audit_router)
    app.dependency_overrides[get_audit_service] = lambda: audit

    set_active_token("test-token")
    transport = ASGITransport(app)
    client = AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    )
    return client, audit, engine


@pytest.mark.asyncio
async def test_list_audit_empty(tmp_path):
    c, _, engine = await _client(tmp_path)
    async with c:
        r = await c.get("/api/v1/audit")
        assert r.status_code == 200
        assert r.json() == {"entries": []}
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_audit_all_entries(tmp_path):
    c, audit, engine = await _client(tmp_path)
    async with c:
        await audit.record(
            AuditEventType.RESOURCE_CREATED.value,
            ref=ResourceRef("mcp_server", "fs"),
            actor="cli",
        )
        await audit.record(
            AuditEventType.RESOURCE_UPDATED.value,
            ref=ResourceRef("mcp_server", "fs"),
            actor="api",
        )
        r = await c.get("/api/v1/audit")
        assert r.status_code == 200
        body = r.json()
        assert len(body["entries"]) == 2
        # newest-first ordering
        assert body["entries"][0]["event_type"] == "resource_updated"
        assert body["entries"][1]["event_type"] == "resource_created"
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_audit_filter_by_kind_name_event(tmp_path):
    c, audit, engine = await _client(tmp_path)
    async with c:
        await audit.record(
            AuditEventType.RESOURCE_CREATED.value,
            ref=ResourceRef("mcp_server", "fs"),
            actor="cli",
        )
        await audit.record(
            AuditEventType.RESOURCE_CREATED.value,
            ref=ResourceRef("mcp_server", "gh"),
            actor="cli",
        )
        await audit.record(
            AuditEventType.RESOURCE_DELETED.value,
            ref=ResourceRef("mcp_server", "fs"),
            actor="cli",
        )

        r = await c.get("/api/v1/audit?name=fs")
        assert r.status_code == 200
        assert len(r.json()["entries"]) == 2

        r = await c.get("/api/v1/audit?event_type=resource_created")
        assert r.status_code == 200
        assert len(r.json()["entries"]) == 2

        r = await c.get("/api/v1/audit?event_type=resource_created&name=fs")
        assert r.status_code == 200
        assert len(r.json()["entries"]) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_audit_since_filter(tmp_path):
    c, audit, engine = await _client(tmp_path)
    async with c:
        await audit.record(
            AuditEventType.RESOURCE_CREATED.value,
            ref=ResourceRef("mcp_server", "x"),
        )
        future = (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat()
        r = await c.get(f"/api/v1/audit?since={future}")
        assert r.status_code == 200
        assert r.json() == {"entries": []}
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_audit_limit(tmp_path):
    c, audit, engine = await _client(tmp_path)
    async with c:
        for i in range(7):
            await audit.record(
                AuditEventType.RESOURCE_CREATED.value,
                ref=ResourceRef("mcp_server", f"r{i}"),
            )
        r = await c.get("/api/v1/audit?limit=3")
        assert r.status_code == 200
        assert len(r.json()["entries"]) == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_audit_requires_token(tmp_path):
    c, _, engine = await _client(tmp_path)
    async with c:
        r = await c.get(
            "/api/v1/audit",
            headers={"X-Coffer-Token": "wrong"},
        )
        assert r.status_code == 401
    await engine.dispose()


def test_parse_since_repairs_unencoded_plus() -> None:
    """_parse_since must handle '+'-containing tz offsets that arrived space-mangled.

    When a client sends ?since=2024-01-15T10:30:00+05:30, browsers and some
    HTTP libraries encode '+' as a space in query strings (x-www-form-urlencoded).
    _parse_since must repair '2024-01-15T10:30:00 05:30' → parse successfully.
    """
    from coffer.surfaces.http.audit_routes import _parse_since

    # Space-mangled tz offset ('+' was decoded as ' ')
    mangled = "2024-01-15T10:30:00 05:30"
    result = _parse_since(mangled)
    assert result is not None
    # The UTC offset must be +05:30 (i.e., +5 h 30 min = 19800 seconds)
    from datetime import timedelta

    assert result.tzinfo is not None
    assert result.utcoffset() == timedelta(hours=5, minutes=30), (
        f"Expected +05:30 offset, got {result.utcoffset()}"
    )

    # None input must return None
    assert _parse_since(None) is None

    # Valid ISO-8601 with explicit + must also parse correctly (no mangling needed)
    valid = "2024-01-15T10:30:00+05:30"
    assert _parse_since(valid) is not None
