"""HTTP contract tests for provider introspection routes (no network)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.providers.ports import ModelIntrospectionService
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.dependencies import set_introspection_service
from coffer.surfaces.http.chat.model_routes import router as model_router
from coffer.surfaces.http.embedding_routes import router as embedding_router

_TOKEN = "t-introspect"


class _FakePort:
    async def list_models(self, *, provider, base_url, api_key):  # type: ignore[no-untyped-def]
        if provider == "broken":
            raise RuntimeError("connection refused")
        return ["gpt-4o", "gpt-4o-mini"]

    async def test_chat(self, *, provider, model, base_url, api_key):  # type: ignore[no-untyped-def]
        if api_key == "bad":
            raise RuntimeError("401 unauthorized")

    async def test_embedding(self, *, provider, model, base_url, api_key):  # type: ignore[no-untyped-def]
        return 1536


@pytest_asyncio.fixture
async def client():  # type: ignore[no-untyped-def]
    set_introspection_service(
        ModelIntrospectionService(_FakePort(), lambda ref: {"ok": "k", "bad-ref": "bad"}[ref])
    )
    app = FastAPI()
    app.include_router(model_router)
    app.include_router(embedding_router)
    err_handlers.register(app)
    set_active_token(_TOKEN)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    ) as c:
        yield c
    set_active_token(None)


@pytest.mark.acceptance(spec="008-agent-chat", scenario="list a provider's models")
async def test_list_models(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/api/v1/models/list-models", json={"provider": "openai", "credential_ref": "ok"})
    assert r.status_code == 200
    assert r.json()["models"] == ["gpt-4o", "gpt-4o-mini"]


async def test_list_models_degrades(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/api/v1/models/list-models", json={"provider": "broken"})
    assert r.status_code == 200
    assert r.json()["models"] == []
    assert "connection refused" in r.json()["message"]


@pytest.mark.acceptance(spec="008-agent-chat", scenario="test a model connection")
async def test_test_connection_ok_and_fail(client) -> None:  # type: ignore[no-untyped-def]
    ok = await client.post(
        "/api/v1/models/test-connection",
        json={"provider": "openai", "model": "gpt-4o", "credential_ref": "ok"},
    )
    assert ok.status_code == 200 and ok.json()["ok"] is True
    bad = await client.post(
        "/api/v1/models/test-connection",
        json={"provider": "openai", "model": "gpt-4o", "credential_ref": "bad-ref"},
    )
    assert bad.status_code == 200 and bad.json()["ok"] is False


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="test an embedding model")
async def test_embedding_test_reports_dimension(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post(
        "/api/v1/embedding/test", json={"provider": "openai", "model": "text-embedding-3-small", "credential_ref": "ok"}
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["detail"]["dimensions"] == 1536


async def test_requires_token(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post(
        "/api/v1/models/list-models", json={"provider": "openai"}, headers={"X-Coffer-Token": "x"}
    )
    assert r.status_code == 401
