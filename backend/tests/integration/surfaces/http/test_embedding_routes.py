"""HTTP-level tests for /api/v1/embedding/config (global embedding singleton)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.application.embedding_config_service import EmbeddingConfigService
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyEmbeddingConfigRepo,
)
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_embedding_config_service
from coffer.surfaces.http.embedding_routes import router as embedding_router

pytestmark = pytest.mark.asyncio


class _FakeCreds:
    """In-memory credential vault for tests (set/delete by ref)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, ref: str, value: str) -> None:
        self.store[ref] = value

    def delete(self, ref: str) -> None:
        self.store.pop(ref, None)


async def _client(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    creds = _FakeCreds()
    svc = EmbeddingConfigService(
        repo=SqlAlchemyEmbeddingConfigRepo(sm),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
        credentials=creds,
    )
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(embedding_router)
    app.dependency_overrides[get_embedding_config_service] = lambda: svc
    set_active_token("test-token")
    client = AsyncClient(
        transport=ASGITransport(app),
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    )
    return client, engine


async def test_get_returns_disabled_default_when_unset(tmp_path):
    client, engine = await _client(tmp_path)
    try:
        r = await client.get("/api/v1/embedding/config")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enabled"] is False
        assert body["provider"] is None
        assert body["dimensions"] == 768
    finally:
        await client.aclose()
        await engine.dispose()


async def test_put_persists_and_get_round_trips(tmp_path):
    client, engine = await _client(tmp_path)
    try:
        put = await client.put(
            "/api/v1/embedding/config",
            json={
                "enabled": True,
                "provider": "local",
                "model": "bge-m3",
                "dimensions": 1024,
            },
            headers={"X-Coffer-Actor": "ui"},
        )
        assert put.status_code == 200, put.text
        assert put.json()["enabled"] is True
        assert put.json()["model"] == "bge-m3"

        got = (await client.get("/api/v1/embedding/config")).json()
        assert got == put.json()
    finally:
        await client.aclose()
        await engine.dispose()


async def test_secret_value_is_stored_and_becomes_the_credential_ref(tmp_path):
    client, engine = await _client(tmp_path)
    try:
        put = await client.put(
            "/api/v1/embedding/config",
            json={
                "enabled": True,
                "provider": "openai",
                "model": "text-embedding-3-small",
                "dimensions": 1536,
                "secret_value": "sk-embed-xyz",
            },
            headers={"X-Coffer-Actor": "ui"},
        )
        assert put.status_code == 200, put.text
        # The raw key is stored in the vault and surfaced only as a fixed ref —
        # never echoed back.
        assert put.json()["credential_ref"] == "embedding/key"
        assert "secret_value" not in put.json()
    finally:
        await client.aclose()
        await engine.dispose()


async def test_enabling_without_provider_model_is_rejected(tmp_path):
    client, engine = await _client(tmp_path)
    try:
        r = await client.put(
            "/api/v1/embedding/config",
            json={"enabled": True, "provider": None, "model": None, "dimensions": 768},
            headers={"X-Coffer-Actor": "ui"},
        )
        # The service raises ValueError → 422 CONFIG_INVALID envelope.
        assert r.status_code == 422, r.text
    finally:
        await client.aclose()
        await engine.dispose()
