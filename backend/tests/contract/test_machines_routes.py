"""Contract tests for the /api/v1/machines fleet-view routes (spec 010
amendment, ADR-045, Task 14).

``GET /api/v1/machines`` mirrors ``GET /api/v1/sync/machines`` (same
registry, same wire shape); ``GET /api/v1/machines/{id}/slice`` computes
that machine's activation slice from the synced registry plus each
resource's machine x agent scope — pure intent math (no local FS/process
checks; those live in existing per-machine endpoints per Task 18).

Colocated under tests/contract (not tests/integration/surfaces/http) because
this is the wire-contract surface for the Machines fleet view specifically.
Fixture style mirrors tests/integration/surfaces/http/test_sync_routes.py
(real SyncService object graph, ASGI transport) and
tests/contract/test_resource_scope_routes.py (lightweight Kind() defs +
direct ResourceService calls to seed scope matrices) — machine-registry
seeding mirrors tests/integration/sync/test_two_machine_sync.py
(``workspace.write_machine_entry`` writes another machine's entry directly,
no actual git sync round-trip needed for this slice math).
"""

from __future__ import annotations

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.config_service import SyncConfigService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.identity import MachineIdentityService
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.service import SyncService
from coffer.domain.resource import Kind
from coffer.domain.sync.models import MachineEntry
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
    SqlAlchemyMachineIdentityRepo,
    SqlAlchemySyncConfigRepo,
    SqlAlchemySyncStateRepo,
)
from coffer.infrastructure.sync.workspace import Workspace
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.machines_routes import router as machines_router
from coffer.surfaces.http.sync_routes import router as sync_router
from coffer.surfaces.http.sync_routes import set_sync_service

_TOKEN = "test-token"
_LOCAL_MACHINE_ID = "01TESTMACHINEAAAAAAAAAAAAA"
_OTHER_MACHINE_ID = "01TESTMACHINEBBBBBBBBBBBBB"


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="allow")


def _kinds() -> dict[str, Kind]:
    return {
        "agent": Kind(
            name="agent",
            display_name="Agent",
            config_schema=_Cfg,
            scope_axes=("machine",),
        ),
        "mcp_server": Kind(
            name="mcp_server",
            display_name="MCP Server",
            config_schema=_Cfg,
            scope_axes=("machine", "agent"),
        ),
        "skill": Kind(
            name="skill",
            display_name="Skill",
            config_schema=_Cfg,
            scope_axes=("machine", "agent"),
        ),
        "channel": Kind(
            name="channel",
            display_name="Channel",
            config_schema=_Cfg,
            scope_axes=("machine",),
        ),
    }


class _NoKeyring:
    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:
        pass

    def delete(self, ref: str) -> None:
        pass


@pytest_asyncio.fixture
async def env(tmp_path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "c.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds=_kinds(),
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    master_key = MasterKeyManager(tmp_path / "master.key", _NoKeyring())
    master_key.resolve(allow_create=True)
    cred_sync = CredentialSyncAdapter(db_path, master_key)
    ws_root = tmp_path / "ws"
    workspace = Workspace(ws_root, trees=[])
    git = GitRepo(ws_root)

    config_svc = SyncConfigService(SqlAlchemySyncConfigRepo(sm), SqlAlchemySyncStateRepo(sm), audit)
    identity = MachineIdentityService(
        SqlAlchemyMachineIdentityRepo(sm),
        audit,
        new_id=lambda: _LOCAL_MACHINE_ID,
        default_name=lambda: "machine-a",
    )
    service = SyncService(
        config=config_svc,
        git=git,
        exporter=SyncExporter(resources, cred_sync, workspace, home=None),
        importer=SyncImporter(resources, cred_sync, workspace, home=None),
        credentials=cred_sync,
        master_key=master_key,
        audit=audit,
        identity=identity,
        workspace=workspace,
        coffer_version="0.0.0-test",
        resources=resources,
    )
    set_sync_service(service)

    app = FastAPI()
    app.include_router(sync_router)
    app.include_router(machines_router)
    app.dependency_overrides[get_resource_service] = lambda: resources
    err_handlers.register(app)
    set_active_token(_TOKEN)
    transport = ASGITransport(app)
    async with AsyncClient(
        transport=transport, base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    ) as c:
        yield type(
            "Env",
            (),
            {"client": c, "resources": resources, "workspace": workspace, "tmp_path": tmp_path},
        )()
    set_active_token(None)
    await engine.dispose()


def _seed_other_machine(workspace: Workspace) -> None:
    workspace.write_machine_entry(
        MachineEntry(
            machine_id=_OTHER_MACHINE_ID,
            display_name="machine-b",
            platform="linux",
            os_version="test",
            coffer_version="0.0.0-test",
            last_sync_at=None,
        )
    )


async def test_list_mirrors_sync_machines(env) -> None:  # type: ignore[no-untyped-def]
    _seed_other_machine(env.workspace)
    r1 = await env.client.get("/api/v1/sync/machines")
    r2 = await env.client.get("/api/v1/machines")
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json()
    machine_ids = {m["machine_id"] for m in r2.json()["machines"]}
    assert machine_ids == {_LOCAL_MACHINE_ID, _OTHER_MACHINE_ID}


async def test_slice_unknown_machine_returns_404(env) -> None:  # type: ignore[no-untyped-def]
    r = await env.client.get("/api/v1/machines/does-not-exist/slice")
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "MACHINE_NOT_FOUND"


async def _seed_matrix(resources: ResourceService) -> None:
    """Seed the activation matrix described in the Task 14 brief:

    - agent "claude-code" scoped to machine A only
    - agent "other-agent" scoped to machine B only
    - mcp_server "fs" dual-axis scoped to {A: ["claude-code"]}
    - skill "notes" left unscoped (active everywhere, for every active agent)
    - channel "tg" scoped to machine A only
    """
    a1 = await resources.register(kind="agent", name="claude-code", config={}, actor="test")
    await resources.update_scope(a1.ref, {_LOCAL_MACHINE_ID: "*"}, actor="test")

    a2 = await resources.register(kind="agent", name="other-agent", config={}, actor="test")
    await resources.update_scope(a2.ref, {_OTHER_MACHINE_ID: "*"}, actor="test")

    m1 = await resources.register(kind="mcp_server", name="fs", config={}, actor="test")
    await resources.update_scope(m1.ref, {_LOCAL_MACHINE_ID: ["claude-code"]}, actor="test")

    await resources.register(kind="skill", name="notes", config={}, actor="test")
    # No scope call: stays None (unscoped).

    c1 = await resources.register(kind="channel", name="tg", config={}, actor="test")
    await resources.update_scope(c1.ref, {_LOCAL_MACHINE_ID: "*"}, actor="test")


async def test_slice_activation_matrix_on_machine_a(env) -> None:  # type: ignore[no-untyped-def]
    _seed_other_machine(env.workspace)
    await _seed_matrix(env.resources)

    r = await env.client.get(f"/api/v1/machines/{_LOCAL_MACHINE_ID}/slice")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["machine"]["machine_id"] == _LOCAL_MACHINE_ID
    assert body["machine"]["is_local"] is True

    agents = {a["name"]: a["active"] for a in body["agents"]}
    assert agents == {"claude-code": True, "other-agent": False}

    mcp_servers = {m["name"]: m for m in body["mcp_servers"]}
    assert mcp_servers["fs"]["active"] is True
    assert mcp_servers["fs"]["agents"] == ["claude-code"]

    skills = {s["name"]: s for s in body["skills"]}
    assert skills["notes"]["active"] is True
    assert skills["notes"]["agents"] == ["claude-code"]

    channels = {c["name"]: c["active"] for c in body["channels"]}
    assert channels == {"tg": True}


async def test_slice_activation_matrix_on_machine_b(env) -> None:  # type: ignore[no-untyped-def]
    _seed_other_machine(env.workspace)
    await _seed_matrix(env.resources)

    r = await env.client.get(f"/api/v1/machines/{_OTHER_MACHINE_ID}/slice")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["machine"]["machine_id"] == _OTHER_MACHINE_ID
    assert body["machine"]["is_local"] is False

    agents = {a["name"]: a["active"] for a in body["agents"]}
    assert agents == {"claude-code": False, "other-agent": True}

    mcp_servers = {m["name"]: m for m in body["mcp_servers"]}
    assert mcp_servers["fs"]["active"] is False
    assert mcp_servers["fs"]["agents"] == []

    skills = {s["name"]: s for s in body["skills"]}
    assert skills["notes"]["active"] is True
    assert skills["notes"]["agents"] == ["other-agent"]

    channels = {c["name"]: c["active"] for c in body["channels"]}
    assert channels == {"tg": False}


async def test_requires_token(env) -> None:  # type: ignore[no-untyped-def]
    r = await env.client.get("/api/v1/machines", headers={"X-Coffer-Token": "wrong"})
    assert r.status_code == 401
