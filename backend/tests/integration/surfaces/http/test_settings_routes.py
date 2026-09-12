"""Integration tests for /api/v1/settings — master key storage, daemon port."""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEntry
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.surfaces.http import daemon_routes
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


# --- /api/v1/settings/daemon (spec mcp-gateway FR-028) ---


def _build_daemon(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    serving_port: int = 8000,
) -> tuple[FastAPI, _FakeAuditRepo]:
    """Same app as _build, but with HOME and the served port pinned.

    HOME decides where daemon_config writes, so pinning it to tmp_path is what
    keeps these tests off the developer's real ~/.coffer.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".coffer").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(daemon_routes, "_PORT", serving_port)
    app, _, audit_repo = _build(tmp_path)
    return app, audit_repo


async def test_daemon_get_reports_automatic_when_unset(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = _build_daemon(tmp_path, monkeypatch, serving_port=8003)
    async with _client(app) as c:
        r = await c.get("/api/v1/settings/daemon")
    assert r.status_code == 200
    assert r.json() == {
        "configured_port": None,
        "effective_port": 8003,
        "restart_required": False,
    }


async def test_daemon_put_sets_port_and_audits(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, audit_repo = _build_daemon(tmp_path, monkeypatch, serving_port=8000)
    async with _client(app) as c:
        r = await c.put("/api/v1/settings/daemon", json={"port": 8000})
        assert r.status_code == 200
        assert r.json() == {
            "configured_port": 8000,
            "effective_port": 8000,
            "restart_required": False,
        }
        # The setting persists for the next reader, not just this response.
        assert (await c.get("/api/v1/settings/daemon")).json()["configured_port"] == 8000
    assert [e.event_type for e in audit_repo.entries] == ["daemon_port_set"]
    assert audit_repo.entries[0].details == {"port": 8000}


async def test_daemon_put_different_port_requires_restart(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = _build_daemon(tmp_path, monkeypatch, serving_port=8002)
    async with _client(app) as c:
        r = await c.put("/api/v1/settings/daemon", json={"port": 9123})
    assert r.status_code == 200
    assert r.json() == {
        "configured_port": 9123,
        "effective_port": 8002,
        "restart_required": True,
    }


async def test_daemon_put_same_port_twice_audits_once(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, audit_repo = _build_daemon(tmp_path, monkeypatch)
    async with _client(app) as c:
        assert (await c.put("/api/v1/settings/daemon", json={"port": 9123})).status_code == 200
        r = await c.put("/api/v1/settings/daemon", json={"port": 9123})
    assert r.status_code == 200
    assert [e.event_type for e in audit_repo.entries] == ["daemon_port_set"]


async def test_daemon_put_null_clears_the_setting(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, audit_repo = _build_daemon(tmp_path, monkeypatch, serving_port=8000)
    async with _client(app) as c:
        await c.put("/api/v1/settings/daemon", json={"port": 9123})
        r = await c.put("/api/v1/settings/daemon", json={"port": None})
        assert r.status_code == 200
        assert r.json() == {
            "configured_port": None,
            "effective_port": 8000,
            "restart_required": False,
        }
        assert (await c.get("/api/v1/settings/daemon")).json()["configured_port"] is None
    assert [e.details for e in audit_repo.entries] == [{"port": 9123}, {"port": None}]


@pytest.mark.parametrize("port", [80, 0, -1, 65536])
async def test_daemon_put_out_of_range_is_400_and_changes_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, port: int
) -> None:
    app, audit_repo = _build_daemon(tmp_path, monkeypatch)
    async with _client(app) as c:
        assert (await c.put("/api/v1/settings/daemon", json={"port": 9123})).status_code == 200
        r = await c.put("/api/v1/settings/daemon", json={"port": port})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "BAD_REQUEST"
        assert (await c.get("/api/v1/settings/daemon")).json()["configured_port"] == 9123
    assert [e.details for e in audit_repo.entries] == [{"port": 9123}]


async def test_daemon_routes_require_a_token(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = _build_daemon(tmp_path, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/v1/settings/daemon")).status_code == 401
        assert (await c.put("/api/v1/settings/daemon", json={"port": 9123})).status_code == 401
