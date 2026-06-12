"""Integration tests for /api/v1/settings/credentials — master key storage toggle."""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEntry
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_audit_service, get_master_key_manager
from coffer.surfaces.http.settings_routes import router as settings_router


class _FakeKeyring:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self.store.get(ref)

    def set(self, ref: str, value: str) -> None:
        self.store[ref] = value

    def delete(self, ref: str) -> None:
        self.store.pop(ref, None)


class _FakeAuditRepo:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def insert(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    async def query(self, **_: Any) -> list[AuditEntry]:
        return list(self.entries)


def _build(tmp_path: pathlib.Path) -> tuple[FastAPI, MasterKeyManager, _FakeAuditRepo]:
    mgr = MasterKeyManager(key_path=tmp_path / "master.key", keyring=_FakeKeyring())
    assert mgr.resolve(allow_create=True) is not None
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(settings_router)
    app.dependency_overrides[get_master_key_manager] = lambda: mgr
    audit_repo = _FakeAuditRepo()
    app.dependency_overrides[get_audit_service] = lambda: AuditService(audit_repo)  # type: ignore[arg-type]
    set_active_token("test-token")
    return app, mgr, audit_repo


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Coffer-Token": "test-token"},
    )


async def test_get_reports_file_by_default(tmp_path: pathlib.Path) -> None:
    app, _, _ = _build(tmp_path)
    async with _client(app) as c:
        r = await c.get("/api/v1/settings/credentials")
    assert r.status_code == 200
    assert r.json() == {"master_key_storage": "file"}


async def test_put_relocates_and_audits(tmp_path: pathlib.Path) -> None:
    app, mgr, audit_repo = _build(tmp_path)
    async with _client(app) as c:
        r = await c.put("/api/v1/settings/credentials", json={"master_key_storage": "keychain"})
    assert r.status_code == 200
    assert r.json() == {"master_key_storage": "keychain"}
    assert mgr.location == "keychain"
    assert [e.event_type for e in audit_repo.entries] == ["master_key_relocated"]


async def test_put_same_location_is_noop(tmp_path: pathlib.Path) -> None:
    app, _, audit_repo = _build(tmp_path)
    async with _client(app) as c:
        r = await c.put("/api/v1/settings/credentials", json={"master_key_storage": "file"})
    assert r.status_code == 200
    assert audit_repo.entries == []


async def test_put_rejects_unknown_value(tmp_path: pathlib.Path) -> None:
    app, _, _ = _build(tmp_path)
    async with _client(app) as c:
        r = await c.put("/api/v1/settings/credentials", json={"master_key_storage": "vault"})
    assert r.status_code == 422
