"""Integration tests for /api/v1/credentials — secret storage endpoint."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEntry
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.credential_routes import router as credential_router
from coffer.surfaces.http.dependencies import get_audit_service, get_credential_store


class _FakeCredentialStore:
    """In-memory stand-in for EncryptedCredentialStore — keeps tests off the real store."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, ref: str, value: str) -> None:
        self.store[ref] = value

    def get(self, ref: str) -> str | None:
        return self.store.get(ref)

    def exists(self, ref: str) -> bool:
        return ref in self.store

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


def _build_app(fake: _FakeCredentialStore, audit_repo: _FakeAuditRepo | None = None) -> FastAPI:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(credential_router)
    app.dependency_overrides[get_credential_store] = lambda: fake
    audit_repo = audit_repo or _FakeAuditRepo()
    audit_svc = AuditService(audit_repo)  # type: ignore[arg-type]
    app.dependency_overrides[get_audit_service] = lambda: audit_svc
    set_active_token("test-token")
    return app


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="store and reference a credential")
@pytest.mark.asyncio
async def test_set_credential_stores_value() -> None:
    fake = _FakeCredentialStore()
    audit_repo = _FakeAuditRepo()
    transport = ASGITransport(_build_app(fake, audit_repo))
    async with AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    ) as c:
        r = await c.post(
            "/api/v1/credentials",
            json={"ref": "github.GITHUB_TOKEN", "value": "ghp_secret"},
        )
        assert r.status_code == 204
    assert fake.store["github.GITHUB_TOKEN"] == "ghp_secret"
    # FR-014: every credential lifecycle change is audited; secret value MUST NOT
    # appear in the audit row — only the ref.
    assert len(audit_repo.entries) == 1
    set_entry = audit_repo.entries[0]
    assert set_entry.event_type == "credential_set"
    assert set_entry.details == {"ref": "github.GITHUB_TOKEN"}
    assert "ghp_secret" not in str(set_entry.details)


@pytest.mark.asyncio
async def test_exists_reports_presence_without_returning_value() -> None:
    fake = _FakeCredentialStore()
    fake.store["github.GITHUB_TOKEN"] = "ghp_secret"
    transport = ASGITransport(_build_app(fake))
    async with AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    ) as c:
        present = await c.get("/api/v1/credentials/github.GITHUB_TOKEN/exists")
        assert present.status_code == 200
        assert present.json() == {"present": True}
        # The secret value must never cross the API for a presence check.
        assert "ghp_secret" not in present.text

        absent = await c.get("/api/v1/credentials/absent.REF/exists")
        assert absent.status_code == 200
        assert absent.json() == {"present": False}


@pytest.mark.asyncio
async def test_exists_requires_token() -> None:
    fake = _FakeCredentialStore()
    fake.store["x"] = "y"
    transport = ASGITransport(_build_app(fake))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/v1/credentials/x/exists")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_returns_value_and_audits_the_read() -> None:
    fake = _FakeCredentialStore()
    fake.store["github.GITHUB_TOKEN"] = "ghp_secret"
    audit_repo = _FakeAuditRepo()
    transport = ASGITransport(_build_app(fake, audit_repo))
    async with AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    ) as c:
        r = await c.get("/api/v1/credentials/github.GITHUB_TOKEN")
        assert r.status_code == 200
        assert r.json() == {"value": "ghp_secret"}
    # The read is audited (ref only — value never in the audit row).
    read_events = [e for e in audit_repo.entries if e.event_type == "credential_read"]
    assert len(read_events) == 1
    assert read_events[0].details == {"ref": "github.GITHUB_TOKEN"}
    assert "ghp_secret" not in str(read_events[0].details)


@pytest.mark.asyncio
async def test_get_missing_ref_returns_404() -> None:
    fake = _FakeCredentialStore()
    transport = ASGITransport(_build_app(fake))
    async with AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    ) as c:
        r = await c.get("/api/v1/credentials/absent.REF")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_requires_token() -> None:
    fake = _FakeCredentialStore()
    fake.store["x"] = "y"
    transport = ASGITransport(_build_app(fake))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/v1/credentials/x")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_set_credential_requires_token() -> None:
    fake = _FakeCredentialStore()
    transport = ASGITransport(_build_app(fake))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/v1/credentials", json={"ref": "x", "value": "y"})
        assert r.status_code == 401
    assert fake.store == {}


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="delete a credential frees the reference")
@pytest.mark.asyncio
async def test_delete_credential_removes_value() -> None:
    fake = _FakeCredentialStore()
    fake.store["github.GITHUB_TOKEN"] = "ghp_secret"
    audit_repo = _FakeAuditRepo()
    transport = ASGITransport(_build_app(fake, audit_repo))
    async with AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    ) as c:
        r = await c.delete("/api/v1/credentials/github.GITHUB_TOKEN")
        assert r.status_code == 204
        # Idempotent — deleting an absent ref still succeeds.
        r2 = await c.delete("/api/v1/credentials/nonexistent.REF")
        assert r2.status_code == 204
    assert fake.store == {}
    # Spec scenario "delete a credential frees the reference":
    # "the deletion is audited" — assert the audit row exists with correct
    # event_type + ref. Both deletes (existing + absent) are recorded since
    # the route is idempotent.
    delete_events = [e for e in audit_repo.entries if e.event_type == "credential_deleted"]
    assert len(delete_events) == 2
    assert delete_events[0].details == {"ref": "github.GITHUB_TOKEN"}
    assert delete_events[1].details == {"ref": "nonexistent.REF"}
    # Actor falls back to "api" when X-Coffer-Actor header is absent.
    assert all(e.actor == "api" for e in delete_events)


@pytest.mark.asyncio
async def test_slash_separated_refs_round_trip() -> None:
    """Channel credentials use slash-separated refs (e.g. channel/tg/bot-token);
    the body pattern must accept them and the {ref:path} routes must round-trip
    set -> exists -> get -> delete without mangling the path."""
    fake = _FakeCredentialStore()
    transport = ASGITransport(_build_app(fake, _FakeAuditRepo()))
    ref = "channel/tg/bot-token"
    async with AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    ) as c:
        r = await c.post("/api/v1/credentials", json={"ref": ref, "value": "123:abc"})
        assert r.status_code == 204
        r = await c.get(f"/api/v1/credentials/{ref}/exists")
        assert r.status_code == 200
        assert r.json() == {"present": True}
        r = await c.get(f"/api/v1/credentials/{ref}")
        assert r.status_code == 200
        assert r.json() == {"value": "123:abc"}
        r = await c.delete(f"/api/v1/credentials/{ref}")
        assert r.status_code == 204
    assert ref not in fake.store


@pytest.mark.asyncio
async def test_malformed_refs_are_rejected() -> None:
    """Leading/trailing/double slashes never reach the store."""
    fake = _FakeCredentialStore()
    transport = ASGITransport(_build_app(fake, _FakeAuditRepo()))
    async with AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    ) as c:
        for bad in ("/leading", "trailing/", "a//b"):
            r = await c.post("/api/v1/credentials", json={"ref": bad, "value": "v"})
            assert r.status_code == 422, bad
    assert fake.store == {}
