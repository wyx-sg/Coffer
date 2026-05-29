"""Integration tests for /api/v1/keychain — secret storage endpoint."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEntry
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_audit_service, get_keyring
from coffer.surfaces.http.keychain_routes import router as keychain_router


class _FakeKeyring:
    """In-memory stand-in for KeyringAdapter — keeps tests off the real keychain."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, ref: str, value: str) -> None:
        self.store[ref] = value

    def delete(self, ref: str) -> None:
        self.store.pop(ref, None)


class _FakeAuditRepo:
    """Captures inserted audit entries for assertions."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def insert(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    async def query(self, **_: Any) -> list[AuditEntry]:
        return list(self.entries)


def _build_app(fake: _FakeKeyring, audit_repo: _FakeAuditRepo | None = None) -> FastAPI:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(keychain_router)
    app.dependency_overrides[get_keyring] = lambda: fake
    audit_repo = audit_repo or _FakeAuditRepo()
    audit_svc = AuditService(audit_repo)  # type: ignore[arg-type]
    app.dependency_overrides[get_audit_service] = lambda: audit_svc
    set_active_token("test-token")
    return app


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="store and reference a keychain credential"
)
@pytest.mark.asyncio
async def test_set_keychain_secret_stores_value() -> None:
    fake = _FakeKeyring()
    audit_repo = _FakeAuditRepo()
    transport = ASGITransport(_build_app(fake, audit_repo))
    async with AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    ) as c:
        r = await c.post(
            "/api/v1/keychain",
            json={"ref": "github.GITHUB_TOKEN", "value": "ghp_secret"},
        )
        assert r.status_code == 204
    assert fake.store["github.GITHUB_TOKEN"] == "ghp_secret"
    # FR-014: every keychain lifecycle change is audited; secret value MUST NOT
    # appear in the audit row — only the ref.
    assert len(audit_repo.entries) == 1
    set_entry = audit_repo.entries[0]
    assert set_entry.event_type == "keychain_set"
    assert set_entry.details == {"ref": "github.GITHUB_TOKEN"}
    assert "ghp_secret" not in str(set_entry.details)


@pytest.mark.asyncio
async def test_set_keychain_secret_requires_token() -> None:
    fake = _FakeKeyring()
    transport = ASGITransport(_build_app(fake))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/v1/keychain", json={"ref": "x", "value": "y"})
        assert r.status_code == 401
    assert fake.store == {}


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="delete a keychain credential frees the reference"
)
@pytest.mark.asyncio
async def test_delete_keychain_secret_removes_value() -> None:
    fake = _FakeKeyring()
    fake.store["github.GITHUB_TOKEN"] = "ghp_secret"
    audit_repo = _FakeAuditRepo()
    transport = ASGITransport(_build_app(fake, audit_repo))
    async with AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    ) as c:
        r = await c.delete("/api/v1/keychain/github.GITHUB_TOKEN")
        assert r.status_code == 204
        # Idempotent — deleting an absent ref still succeeds.
        r2 = await c.delete("/api/v1/keychain/nonexistent.REF")
        assert r2.status_code == 204
    assert fake.store == {}
    # Spec scenario "delete a keychain credential frees the reference":
    # "the deletion is audited" — assert the audit row exists with correct
    # event_type + ref. Both deletes (existing + absent) are recorded since
    # the route is idempotent.
    delete_events = [e for e in audit_repo.entries if e.event_type == "keychain_deleted"]
    assert len(delete_events) == 2
    assert delete_events[0].details == {"ref": "github.GITHUB_TOKEN"}
    assert delete_events[1].details == {"ref": "nonexistent.REF"}
    # Actor falls back to "api" when X-Coffer-Actor header is absent.
    assert all(e.actor == "api" for e in delete_events)
