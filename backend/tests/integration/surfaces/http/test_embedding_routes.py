"""HTTP-level tests for /api/v1/embedding/config (global embedding singleton).

The config NAMES a connection rather than restating one, so these drive the real
route over the real composition-root adapter (``_ProviderEndpoints``) sitting on
a fake provider service: what the route accepts or refuses is decided by the
connection's own ``ProviderConfig`` — its protocol and its curated
``embedding``-modality models — exactly as it is in the daemon.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.application.embedding_config_service import EmbeddingConfigService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.provider.config import ProviderConfig
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
from coffer.surfaces.http.app_embedding_composition import _ProviderEndpoints
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_embedding_config_service
from coffer.surfaces.http.dependencies_agent import set_provider_service
from coffer.surfaces.http.embedding_routes import router as embedding_router

pytestmark = pytest.mark.asyncio

# A rejected config is the app-wide CONFIG_INVALID envelope. NOTE: specs/knowledge
# spec.md calls this "HTTP 400"; the app-wide handler maps CONFIG_INVALID to 422
# (as it does for every other config rejection), so the code answers 422 here.
_REFUSED = 422


@pytest.fixture(autouse=True)
def _restore_process_globals():
    """``_ProviderEndpoints`` resolves the provider service through a module
    global; put it back so a test here cannot decide what a later one sees."""
    yield
    set_provider_service(None)
    set_active_token(None)


class _FakeProviderService:
    """The provider kind, narrowed to the one call ``_ProviderEndpoints`` makes."""

    def __init__(self) -> None:
        self.configs: dict[str, dict[str, object]] = {}

    def register(self, name: str, **config: object) -> None:
        """Register a connection, validated through the real ``ProviderConfig``."""
        self.configs[name] = ProviderConfig.model_validate(config).model_dump(mode="json")

    async def get(self, name: str):  # type: ignore[no-untyped-def]
        if name not in self.configs:
            raise ResourceNotFound("provider", name)
        return SimpleNamespace(name=name, config=self.configs[name])


async def _harness(tmp_path):
    """Return ``(client, engine, svc, providers)``; the caller closes the first two."""
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    providers = _FakeProviderService()
    set_provider_service(providers)
    svc = EmbeddingConfigService(
        repo=SqlAlchemyEmbeddingConfigRepo(sm),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
        connections=_ProviderEndpoints(),
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
    return client, engine, svc, providers


def _openai_with_embedding(providers: _FakeProviderService, name: str = "acme") -> None:
    """A connection curating one embedding model and one chat model."""
    providers.register(
        name,
        protocol="openai",
        base_url="https://api.openai.com/v1",
        credential_ref=f"provider/{name}/key",
        models=[
            {"id": "text-embedding-3-large", "modality": "embedding"},
            {"id": "gpt-4o", "modality": "text"},
        ],
    )


async def test_get_returns_disabled_default_when_unset(tmp_path):
    client, engine, _svc, _providers = await _harness(tmp_path)
    try:
        r = await client.get("/api/v1/embedding/config")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enabled"] is False
        assert body["connection"] is None
        assert body["model"] is None
        assert body["dimensions"] == 768
    finally:
        await client.aclose()
        await engine.dispose()


async def test_put_persists_and_get_round_trips(tmp_path):
    client, engine, _svc, providers = await _harness(tmp_path)
    try:
        _openai_with_embedding(providers)
        put = await client.put(
            "/api/v1/embedding/config",
            json={
                "enabled": True,
                "connection": "acme",
                "model": "text-embedding-3-large",
                "dimensions": 1024,
            },
            headers={"X-Coffer-Actor": "ui"},
        )
        assert put.status_code == 200, put.text
        assert put.json()["enabled"] is True
        assert put.json()["connection"] == "acme"
        assert put.json()["model"] == "text-embedding-3-large"

        got = (await client.get("/api/v1/embedding/config")).json()
        assert got == put.json()
    finally:
        await client.aclose()
        await engine.dispose()


async def test_config_holds_no_secret_and_takes_the_key_from_the_connection(tmp_path):
    """The config mints no vault entry of its own any more (there is no
    ``secret_value`` field and no ``embedding/key`` ref): the wire, base URL and
    credential all come from the NAMED connection when the embedder is built."""
    client, engine, svc, providers = await _harness(tmp_path)
    try:
        _openai_with_embedding(providers)
        put = await client.put(
            "/api/v1/embedding/config",
            json={
                "enabled": True,
                "connection": "acme",
                "model": "text-embedding-3-large",
                "dimensions": 1536,
                # A stale client still sending a key: the field is gone, so it is
                # ignored rather than stored, and nothing is echoed back.
                "secret_value": "sk-embed-xyz",
            },
            headers={"X-Coffer-Actor": "ui"},
        )
        assert put.status_code == 200, put.text
        body = put.json()
        for gone in ("provider", "base_url", "credential_ref", "secret_value"):
            assert gone not in body

        resolved = await svc.resolve()
        assert resolved is not None
        assert resolved.provider == "openai"
        assert resolved.base_url == "https://api.openai.com/v1"
        assert resolved.credential_ref == "provider/acme/key"
        assert resolved.dimensions == 1536
    finally:
        await client.aclose()
        await engine.dispose()


async def test_enabling_without_connection_model_is_rejected(tmp_path):
    client, engine, _svc, _providers = await _harness(tmp_path)
    try:
        r = await client.put(
            "/api/v1/embedding/config",
            json={"enabled": True, "connection": None, "model": None, "dimensions": 768},
            headers={"X-Coffer-Actor": "ui"},
        )
        assert r.status_code == _REFUSED, r.text
        assert r.json()["error"]["code"] == "CONFIG_INVALID"
        assert "required to enable embedding" in r.json()["error"]["message"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_unknown_connection_is_refused(tmp_path):
    client, engine, _svc, _providers = await _harness(tmp_path)
    try:
        r = await client.put(
            "/api/v1/embedding/config",
            json={"enabled": True, "connection": "ghost", "model": "e5", "dimensions": 768},
            headers={"X-Coffer-Actor": "ui"},
        )
        assert r.status_code == _REFUSED, r.text
        assert "no connection named 'ghost'" in r.json()["error"]["message"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_anthropic_connection_is_refused(tmp_path):
    """That wire exposes no embeddings API, so naming it is refused up front
    rather than producing a config that silently cannot embed."""
    client, engine, _svc, providers = await _harness(tmp_path)
    try:
        providers.register(
            "claude",
            protocol="anthropic",
            base_url="https://api.anthropic.com",
            credential_ref="provider/claude/key",
        )
        r = await client.put(
            "/api/v1/embedding/config",
            json={
                "enabled": True,
                "connection": "claude",
                "model": "text-embedding-3-large",
                "dimensions": 768,
            },
            headers={"X-Coffer-Actor": "ui"},
        )
        assert r.status_code == _REFUSED, r.text
        message = r.json()["error"]["message"]
        assert "anthropic" in message and "serves no " in message
    finally:
        await client.aclose()
        await engine.dispose()


async def test_connection_curating_only_text_models_is_refused(tmp_path):
    """It curates a set, and that set holds no ``embedding`` entry — a different
    answer from curating nothing at all, which means "no restriction"."""
    client, engine, _svc, providers = await _harness(tmp_path)
    try:
        providers.register(
            "chat-only",
            protocol="openai",
            base_url="https://gw/v1",
            credential_ref="provider/chat-only/key",
            models=[{"id": "gpt-4o", "modality": "text"}],
        )
        r = await client.put(
            "/api/v1/embedding/config",
            json={
                "enabled": True,
                "connection": "chat-only",
                "model": "text-embedding-3-large",
                "dimensions": 768,
            },
            headers={"X-Coffer-Actor": "ui"},
        )
        assert r.status_code == _REFUSED, r.text
        assert "offers no embedding model" in r.json()["error"]["message"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_model_the_connection_does_not_offer_is_refused(tmp_path):
    client, engine, _svc, providers = await _harness(tmp_path)
    try:
        _openai_with_embedding(providers)
        r = await client.put(
            "/api/v1/embedding/config",
            json={
                "enabled": True,
                "connection": "acme",
                "model": "bge-m3",
                "dimensions": 768,
            },
            headers={"X-Coffer-Actor": "ui"},
        )
        assert r.status_code == _REFUSED, r.text
        message = r.json()["error"]["message"]
        assert "does not offer embedding model 'bge-m3'" in message
        # The message names what it DOES offer, and only the embedding one.
        assert "text-embedding-3-large" in message
        assert "gpt-4o" not in message
    finally:
        await client.aclose()
        await engine.dispose()


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="the global embedding model is chosen from a connection",
)
async def test_global_embedding_model_is_chosen_from_a_connection(tmp_path):
    """End to end: a connection is registered, the installation-wide config names
    it plus one of its embedding models, and the round-tripped config carries
    only that name — no restated provider, base URL or credential."""
    client, engine, _svc, providers = await _harness(tmp_path)
    try:
        _openai_with_embedding(providers)

        put = await client.put(
            "/api/v1/embedding/config",
            json={
                "enabled": True,
                "connection": "acme",
                "model": "text-embedding-3-large",
                "dimensions": 3072,
                "default_chunk_size": 512,
                "default_chunk_overlap": 64,
            },
            headers={"X-Coffer-Actor": "ui"},
        )
        assert put.status_code == 200, put.text

        got = await client.get("/api/v1/embedding/config")
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["connection"] == "acme"
        assert body["model"] == "text-embedding-3-large"
        assert body["enabled"] is True
        assert body["dimensions"] == 3072
        assert set(body) == {
            "enabled",
            "connection",
            "model",
            "dimensions",
            "default_chunk_size",
            "default_chunk_overlap",
            "updated_at",
        }
        for gone in ("provider", "base_url", "credential_ref"):
            assert gone not in body
    finally:
        await client.aclose()
        await engine.dispose()
