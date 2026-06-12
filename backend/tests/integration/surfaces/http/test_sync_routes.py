"""HTTP contract tests for /api/v1/sync (spec 010)."""

from __future__ import annotations

import subprocess

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.config_service import SyncConfigService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.service import SyncService
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.infrastructure.sync.git_repo import GitRepo
from coffer.infrastructure.sync.persistence import (
    SqlAlchemySyncConfigRepo,
    SqlAlchemySyncStateRepo,
)
from coffer.infrastructure.sync.workspace import Workspace
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.sync_routes import router as sync_router
from coffer.surfaces.http.sync_routes import set_sync_service

_TOKEN = "test-token"


class _Cfg(BaseModel):
    value: str = ""


class _NoKeyring:
    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:
        pass

    def delete(self, ref: str) -> None:
        pass


@pytest_asyncio.fixture
async def client(tmp_path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "c.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={"mcp_server": Kind(name="mcp_server", display_name="X", config_schema=_Cfg)},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    master_key = MasterKeyManager(tmp_path / "master.key", _NoKeyring())
    master_key.resolve(allow_create=True)
    cred_sync = CredentialSyncAdapter(db_path, master_key)
    workspace = Workspace(tmp_path / "ws", trees=[])
    git = GitRepo(tmp_path / "ws")
    config_svc = SyncConfigService(SqlAlchemySyncConfigRepo(sm), SqlAlchemySyncStateRepo(sm), audit)
    service = SyncService(
        config=config_svc,
        git=git,
        exporter=SyncExporter(resources, cred_sync, workspace),
        importer=SyncImporter(resources, cred_sync, workspace),
        credentials=cred_sync,
        master_key=master_key,
        audit=audit,
        machine_id="test",
    )
    set_sync_service(service)

    app = FastAPI()
    app.include_router(sync_router)
    err_handlers.register(app)
    set_active_token(_TOKEN)
    transport = ASGITransport(app)
    async with AsyncClient(
        transport=transport, base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    ) as c:
        c.tmp_path = tmp_path  # type: ignore[attr-defined]
        yield c
    set_active_token(None)
    await engine.dispose()


async def test_config_get_defaults_then_put(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/v1/sync/config")
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["interval_seconds"] == 300

    bare = client.tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    r = await client.put(
        "/api/v1/sync/config",
        json={
            "remote": str(bare),
            "enabled": True,
            "auto": False,
            "interval_seconds": 120,
            "branch": "main",
        },
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert r.json()["interval_seconds"] == 120


async def test_put_config_rejects_short_interval(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.put(
        "/api/v1/sync/config",
        json={
            "remote": "x",
            "enabled": False,
            "auto": False,
            "interval_seconds": 5,
            "branch": "main",
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "CONFIG_INVALID"


async def test_run_unconfigured_is_conflict(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/api/v1/sync/run")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "SYNC_NOT_CONFIGURED"


async def test_status_unconfigured(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/v1/sync/status")
    assert r.status_code == 200
    assert r.json()["status"] == "unconfigured"


@pytest.mark.acceptance(spec="010-sync", scenario="initialise sync against a user remote")
async def test_configure_and_run_clean(client) -> None:  # type: ignore[no-untyped-def]
    bare = client.tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    await client.put(
        "/api/v1/sync/config",
        json={
            "remote": str(bare),
            "enabled": True,
            "auto": False,
            "interval_seconds": 300,
            "branch": "main",
        },
    )
    r = await client.post("/api/v1/sync/run")
    assert r.status_code == 200
    assert r.json()["status"] == "clean"


async def test_requires_token(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/v1/sync/config", headers={"X-Coffer-Token": "wrong"})
    assert r.status_code == 401
