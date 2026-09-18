from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Kind
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
from coffer.surfaces.http.audit_routes import router as audit_router
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_audit_service, get_resource_service


class _FakeConfig(BaseModel):
    foo: int = 0


async def _client(tmp_path):
    """The audit route now resolves ``resource_uid`` through the resource
    service before querying, so the app needs both wired.

    That resolution is the point: the route answers "this resource's trail",
    and a uid nobody knows is a 404 rather than an empty list — "no such
    resource" and "that resource has no events" are different answers.
    """
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={
            "mcp_server": Kind(
                name="mcp_server",
                display_name="MCP Server",
                config_schema=_FakeConfig,
            )
        },
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(audit_router)
    app.dependency_overrides[get_audit_service] = lambda: audit
    app.dependency_overrides[get_resource_service] = lambda: resources

    set_active_token("test-token")
    transport = ASGITransport(app)
    client = AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    )
    return client, audit, resources, engine


async def _register(resources: ResourceService, name: str):
    return await resources.register(kind="mcp_server", name=name, config={"foo": 1}, actor="cli")


@pytest.mark.asyncio
async def test_list_audit_empty(tmp_path):
    c, _, _, engine = await _client(tmp_path)
    async with c:
        r = await c.get("/api/v1/audit")
        assert r.status_code == 200
        assert r.json() == {"entries": []}
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_audit_all_entries(tmp_path):
    c, audit, resources, engine = await _client(tmp_path)
    async with c:
        fs = await _register(resources, "fs")
        await audit.record(
            AuditEventType.RESOURCE_UPDATED.value,
            resource=fs,
            actor="api",
        )
        r = await c.get("/api/v1/audit")
        assert r.status_code == 200
        body = r.json()
        # The register itself audited a resource_created, so there are two.
        assert len(body["entries"]) == 2
        # newest-first ordering
        assert body["entries"][0]["event_type"] == "resource_updated"
        assert body["entries"][1]["event_type"] == "resource_created"
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_audit_filter_by_resource_uid_and_event(tmp_path):
    """Was ``?name=``. The trail is asked for by the RESOURCE now.

    Filtering by label could not tell a renamed resource from a deleted one
    whose name was later reused, so it rendered two objects' histories as one;
    the ``resource_uid`` filter cannot, because a uid is never reissued.
    """
    c, audit, resources, engine = await _client(tmp_path)
    async with c:
        fs = await _register(resources, "fs")
        await _register(resources, "gh")
        await audit.record(AuditEventType.RESOURCE_DELETED.value, resource=fs, actor="cli")

        r = await c.get(f"/api/v1/audit?resource_uid={fs.uid}")
        assert r.status_code == 200
        assert len(r.json()["entries"]) == 2

        r = await c.get("/api/v1/audit?event_type=resource_created")
        assert r.status_code == 200
        assert len(r.json()["entries"]) == 2

        r = await c.get(f"/api/v1/audit?event_type=resource_created&resource_uid={fs.uid}")
        assert r.status_code == 200
        assert len(r.json()["entries"]) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_renamed_resource_still_has_one_trail(tmp_path):
    """Every row keeps the label of its moment, and they all come back together
    — the uid in the query is what ties them, not the name in the rows."""
    c, _audit, resources, engine = await _client(tmp_path)
    async with c:
        fs = await _register(resources, "before")
        await resources.rename(fs.uid, "after", actor="cli")

        r = await c.get(f"/api/v1/audit?resource_uid={fs.uid}")
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert [e["event_type"] for e in entries] == ["resource_renamed", "resource_created"]
        assert [e["resource_name"] for e in entries] == ["after", "before"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_unknown_resource_uid_returns_404(tmp_path):
    """Not an empty list: the caller acts differently on "no such resource"
    than on "that resource has nothing recorded yet"."""
    c, _, _, engine = await _client(tmp_path)
    async with c:
        r = await c.get("/api/v1/audit?resource_uid=no-such-uid")
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_audit_since_filter(tmp_path):
    c, audit, resources, engine = await _client(tmp_path)
    async with c:
        x = await _register(resources, "x")
        await audit.record(AuditEventType.RESOURCE_CREATED.value, resource=x)
        future = (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat()
        r = await c.get(f"/api/v1/audit?since={future}")
        assert r.status_code == 200
        assert r.json() == {"entries": []}
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_audit_limit(tmp_path):
    c, audit, resources, engine = await _client(tmp_path)
    async with c:
        for i in range(7):
            r_i = await _register(resources, f"r{i}")
            await audit.record(AuditEventType.RESOURCE_CREATED.value, resource=r_i)
        r = await c.get("/api/v1/audit?limit=3")
        assert r.status_code == 200
        assert len(r.json()["entries"]) == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_audit_requires_token(tmp_path):
    c, _, _, engine = await _client(tmp_path)
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
