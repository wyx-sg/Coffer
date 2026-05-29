# backend/tests/integration/surfaces/http/test_resource_routes.py
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
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
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router


class _FakeConfig(BaseModel):
    foo: int
    bar: str = "default"


async def _client(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    kinds = {
        "fake_kind": Kind(
            name="fake_kind",
            display_name="Fake",
            config_schema=_FakeConfig,
        ),
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
    return client, engine


@pytest.mark.asyncio
async def test_register_resource(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}, "description": "hi"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["ref"] == "fake_kind:t"
        assert body["kind"] == "fake_kind"
        assert body["config"] == {"foo": 1, "bar": "default"}
        assert body["enabled"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_duplicate_returns_409(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}},
        )
        r = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 2}},
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "RESOURCE_ALREADY_EXISTS"
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_unknown_kind_returns_400(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.post(
            "/api/v1/resources",
            json={"kind": "nope", "name": "t", "config": {}},
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "UNKNOWN_KIND"
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_invalid_config_returns_422(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": "not_int"}},
        )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "CONFIG_INVALID"
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_resources(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "a", "config": {"foo": 1}},
        )
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "b", "config": {"foo": 2}},
        )
        r = await c.get("/api/v1/resources")
        assert r.status_code == 200
        names = sorted(item["name"] for item in r.json()["resources"])
        assert names == ["a", "b"]
        # Filter by kind
        r = await c.get("/api/v1/resources?kind=fake_kind")
        assert r.status_code == 200
        assert len(r.json()["resources"]) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_resource(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}},
        )
        r = await c.get("/api/v1/resources/fake_kind/t")
        assert r.status_code == 200
        assert r.json()["name"] == "t"
        # Not found
        r = await c.get("/api/v1/resources/fake_kind/nope")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_resource_config(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}},
        )
        r = await c.patch(
            "/api/v1/resources/fake_kind/t",
            json={"config": {"foo": 99}, "description": "new desc"},
        )
        assert r.status_code == 200
        assert r.json()["config"]["foo"] == 99
        assert r.json()["description"] == "new desc"
    await engine.dispose()


@pytest.mark.asyncio
async def test_enable_disable(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}},
        )
        r = await c.post("/api/v1/resources/fake_kind/t/disable")
        assert r.status_code == 200
        assert r.json()["enabled"] is False
        r = await c.post("/api/v1/resources/fake_kind/t/enable")
        assert r.status_code == 200
        assert r.json()["enabled"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_resource(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}},
        )
        r = await c.delete("/api/v1/resources/fake_kind/t")
        assert r.status_code == 204
        r = await c.get("/api/v1/resources/fake_kind/t")
        assert r.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_resource_create_enforces_name_pattern(tmp_path):
    """D5: POST /api/v1/resources with an invalid name returns 422."""
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "bad name!", "config": {"foo": 1}},
        )
        assert r.status_code == 422, r.text
    await engine.dispose()


class _StubKeyring:
    """Minimal KeyringPort stand-in for register-time credential probing."""

    def __init__(self, store: dict[str, str] | None = None) -> None:
        self.store: dict[str, str] = dict(store or {})

    def get(self, ref: str) -> str | None:
        return self.store.get(ref)

    def set(self, ref: str, value: str) -> None:
        self.store[ref] = value

    def delete(self, ref: str) -> None:
        self.store.pop(ref, None)


async def _client_with_mcp_kind(tmp_path, keyring: _StubKeyring):
    """Like _client(), but registers the real `mcp_server` Kind so we can
    drive register-time credential probing against transport.credential_refs."""
    from coffer.domain.mcp.server_config import MCPServerConfig

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    kinds = {
        "mcp_server": Kind(
            name="mcp_server",
            display_name="MCP Server",
            config_schema=MCPServerConfig,
        ),
    }
    repo = SqlAlchemyResourceRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    svc = ResourceService(kinds=kinds, repo=repo, audit=audit, keyring=keyring)

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(resource_router)
    app.dependency_overrides[get_resource_service] = lambda: svc

    set_active_token("test-token")
    transport = ASGITransport(app)
    client = AsyncClient(
        transport=transport, base_url="http://t", headers={"X-Coffer-Token": "test-token"}
    )
    return client, engine, repo


@pytest.mark.asyncio
async def test_register_with_missing_credential_returns_actionable_error(tmp_path):
    """Spec edge case: registering an MCP server whose transport.credential_refs
    cites a key absent from the keychain must fail BEFORE any DB write, name
    the missing ref in the error body, and leave the resources table unchanged.
    """
    keyring = _StubKeyring()  # empty — no credentials stored
    c, engine, repo = await _client_with_mcp_kind(tmp_path, keyring)
    async with c:
        before = await repo.list()
        before_count = len(before)
        r = await c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "remote",
                "config": {
                    "transport": {
                        "type": "http",
                        "url": "http://example.com/mcp",
                        "credential_refs": {"Authorization": "github.GITHUB_TOKEN"},
                    },
                },
            },
        )
        # 400 per the existing CREDENTIAL_MISSING -> HTTP mapping in errors.py.
        assert r.status_code == 400, r.text
        body = r.json()
        assert body["error"]["code"] == "CREDENTIAL_MISSING"
        # The missing ref must be named in the message so the user can act.
        assert "github.GITHUB_TOKEN" in body["error"]["message"]
        # No partial state — the resources table is unchanged.
        after = await repo.list()
        assert len(after) == before_count
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_with_present_credential_succeeds(tmp_path):
    """Counterpart: with the credential present in the keychain, registration
    proceeds normally."""
    keyring = _StubKeyring({"github.GITHUB_TOKEN": "ghp_xxx"})
    c, engine, _repo = await _client_with_mcp_kind(tmp_path, keyring)
    async with c:
        r = await c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "remote",
                "config": {
                    "transport": {
                        "type": "http",
                        "url": "http://example.com/mcp",
                        "credential_refs": {"Authorization": "github.GITHUB_TOKEN"},
                    },
                },
            },
        )
        assert r.status_code == 201, r.text
    await engine.dispose()
