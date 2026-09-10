"""HTTP contract tests for /api/v1/sync (spec vault-export-import vault export/import)."""

from __future__ import annotations

import json

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.service import SyncService
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
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
from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
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
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    trees = [("knowledge", knowledge)]

    service = SyncService(
        exporter=SyncExporter(resources, cred_sync, home=None),
        importer=SyncImporter(resources, cred_sync, home=None),
        credentials=cred_sync,
        master_key=master_key,
        audit=audit,
        bundle_factory=lambda p: Bundle(p, trees=trees),
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
        c.resources = resources  # type: ignore[attr-defined]
        c.db_path = db_path  # type: ignore[attr-defined]
        c.master_key = master_key  # type: ignore[attr-defined]
        yield c
    set_active_token(None)
    await engine.dispose()


async def test_export_then_import_round_trip(client) -> None:  # type: ignore[no-untyped-def]
    await client.resources.register("mcp_server", "files", {"value": "a"}, "user")
    (client.tmp_path / "knowledge" / "n.md").write_text("hi", encoding="utf-8")
    out = client.tmp_path / "bundle"

    r = await client.post("/api/v1/sync/export", json={"path": str(out)})
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == str(out)
    assert body["credentials_included"] is False
    assert {a["area"]: a["count"] for a in body["areas"]}["resources"] == 1
    assert body["failures"] == []

    r = await client.post("/api/v1/sync/import", json={"path": str(out)})
    assert r.status_code == 200
    body = r.json()
    assert {a["area"]: a["count"] for a in body["areas"]}["resources"] == 1
    assert body["locked_refs"] == []


async def test_export_with_credentials_is_opt_in(client) -> None:  # type: ignore[no-untyped-def]
    key = client.master_key.export_key()
    assert key is not None
    EncryptedCredentialStore(client.db_path, key).set("mcp/files/token", "s3cret")

    plain = client.tmp_path / "plain"
    r = await client.post("/api/v1/sync/export", json={"path": str(plain)})
    assert r.json()["credentials_included"] is False
    assert not (plain / "credentials").exists()

    withcreds = client.tmp_path / "withcreds"
    r = await client.post(
        "/api/v1/sync/export", json={"path": str(withcreds), "with_credentials": True}
    )
    assert r.json()["credentials_included"] is True
    assert (withcreds / "credentials" / "mcp" / "files" / "token.enc").exists()


async def test_import_of_a_newer_bundle_is_409(client) -> None:  # type: ignore[no-untyped-def]
    out = client.tmp_path / "bundle"
    await client.post("/api/v1/sync/export", json={"path": str(out)})
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["schema_version"] += 1
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    r = await client.post("/api/v1/sync/import", json={"path": str(out)})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "SYNC_BUNDLE_TOO_NEW"


async def test_import_of_a_non_bundle_is_422(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/api/v1/sync/import", json={"path": str(client.tmp_path / "nope")})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SYNC_BUNDLE_INVALID"


async def test_key_fingerprint_never_returns_the_key(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/v1/sync/key/fingerprint")
    assert r.status_code == 200
    body = r.json()
    assert body["present"] is True
    assert len(body["fingerprint"]) == 12
    key = client.master_key.export_key()
    assert key is not None
    assert body["fingerprint"] not in key.decode()


async def test_key_export_then_import(client) -> None:  # type: ignore[no-untyped-def]
    """The key crosses as material, not as a path the daemon writes: a browser
    has no path to hand over, and the caller decides where the bytes land."""
    r = await client.post("/api/v1/sync/key/export", json={})
    assert r.status_code == 200
    material = r.json()["material"]
    assert material

    r = await client.post("/api/v1/sync/key/import", json={"material": material})
    assert r.status_code == 200
    assert r.json()["locked_refs"] == []


async def test_key_import_of_empty_material_is_422(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/api/v1/sync/key/import", json={"material": "   "})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "MASTER_KEY_FILE_INVALID"


async def test_key_import_of_junk_material_is_422(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/api/v1/sync/key/import", json={"material": "not-a-fernet-key"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "MASTER_KEY_FILE_INVALID"


async def test_routes_require_the_token(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post(
        "/api/v1/sync/export",
        json={"path": str(client.tmp_path / "x")},
        headers={"X-Coffer-Token": "wrong"},
    )
    assert r.status_code == 401


async def test_withdrawn_continuous_sync_routes_are_gone(client) -> None:  # type: ignore[no-untyped-def]
    # Vault export/import withdrew continuous sync; its surface must not linger.
    assert (await client.get("/api/v1/sync/config")).status_code == 404
    assert (await client.get("/api/v1/sync/status")).status_code == 404
    assert (await client.post("/api/v1/sync/run", json={})).status_code == 404
    assert (await client.get("/api/v1/sync/machines")).status_code == 404
    assert (await client.get("/api/v1/sync/overrides")).status_code == 404
