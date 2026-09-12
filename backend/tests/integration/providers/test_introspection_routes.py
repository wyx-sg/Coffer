"""HTTP contract tests for provider introspection routes (no network)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.providers.ports import ModelIntrospectionService
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.embedding_routes import router as embedding_router
from coffer.surfaces.http.model_routes import router as model_router
from coffer.surfaces.http.turn_dependencies import set_introspection_service

_TOKEN = "t-introspect"


class _FakePort:
    async def list_models(self, *, provider, base_url, api_key):  # type: ignore[no-untyped-def]
        if provider == "broken":
            raise RuntimeError("connection refused")
        # An endpoint reports ids, never their kind — the third one is what makes
        # the route's inferred modality visible.
        return ["gpt-4o", "gpt-4o-mini", "text-embedding-3-small"]

    async def test_chat(self, *, provider, model, base_url, api_key):  # type: ignore[no-untyped-def]
        if api_key == "bad":
            raise RuntimeError("401 unauthorized")

    async def test_embedding(self, *, provider, model, base_url, api_key):  # type: ignore[no-untyped-def]
        return 1536

    async def detect_protocol(self, *, base_url, api_key):  # type: ignore[no-untyped-def]
        if api_key == "bad":
            raise RuntimeError("auth failed")
        return "openai"


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


@pytest.mark.acceptance(spec="provider-switching", scenario="list a provider's models")
async def test_list_models(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post(
        "/api/v1/models/list-models", json={"provider": "openai", "credential_ref": "ok"}
    )
    assert r.status_code == 200
    # Each id comes back with a modality GUESSED from its name, so the
    # connection's model table pre-fills a kind the user can correct.
    assert r.json()["models"] == [
        {"id": "gpt-4o", "modality": "text"},
        {"id": "gpt-4o-mini", "modality": "text"},
        {"id": "text-embedding-3-small", "modality": "embedding"},
    ]


async def test_list_models_degrades(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/api/v1/models/list-models", json={"provider": "broken"})
    assert r.status_code == 200
    assert r.json()["models"] == []
    assert "connection refused" in r.json()["message"]


@pytest.mark.acceptance(spec="provider-switching", scenario="test a model connection")
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


@pytest.mark.acceptance(spec="knowledge", scenario="test an embedding model")
async def test_embedding_test_reports_dimension(client) -> None:  # type: ignore[no-untyped-def]
    """The probe names a CONNECTION and a model; the protocol, base URL and
    credential are resolved from that connection, never typed into the body."""
    from coffer.application.embedding_config_service import EmbeddingConfigService
    from coffer.domain.embedding_config import EmbeddingEndpoint
    from coffer.surfaces.http.dependencies import set_embedding_config_service

    class _Connections:
        """One configured connection, curating a single embedding model."""

        async def endpoint(self, name: str) -> EmbeddingEndpoint | None:
            if name != "acme":
                return None
            return EmbeddingEndpoint(
                protocol="openai",
                base_url="https://api.openai.com/v1",
                credential_ref="ok",
                offered_models=("text-embedding-3-small",),
            )

    # Only ``endpoint_for`` is exercised here, and it reads nothing but the
    # connections port — the repo and audit log stay out of this route.
    set_embedding_config_service(
        EmbeddingConfigService(repo=None, audit=None, connections=_Connections())  # type: ignore[arg-type]
    )
    try:
        r = await client.post(
            "/api/v1/embedding/test",
            json={"connection": "acme", "model": "text-embedding-3-small"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["detail"]["dimensions"] == 1536

        # A name no connection holds is refused by the same rule that would
        # refuse saving it, so a green test means the settings can be saved.
        missing = await client.post(
            "/api/v1/embedding/test",
            json={"connection": "ghost", "model": "text-embedding-3-small"},
        )
        assert missing.status_code == 422
        assert "no connection named 'ghost'" in missing.json()["error"]["message"]
    finally:
        set_embedding_config_service(None)  # type: ignore[arg-type]


async def test_inline_secret_reaches_port(client) -> None:  # type: ignore[no-untyped-def]
    # An inline secret (no credential_ref) flows straight to the port: "bad"
    # triggers the fake port's 401, proving the typed key was used as-is.
    r = await client.post(
        "/api/v1/models/test-connection",
        json={"provider": "openai", "model": "gpt-4o", "secret_value": "bad"},
    )
    assert r.status_code == 200 and r.json()["ok"] is False
    ok = await client.post(
        "/api/v1/models/list-models",
        json={"provider": "openai", "secret_value": "sk-inline"},
    )
    assert ok.status_code == 200
    assert [m["id"] for m in ok.json()["models"]] == [
        "gpt-4o",
        "gpt-4o-mini",
        "text-embedding-3-small",
    ]


async def test_detect_protocol(client) -> None:  # type: ignore[no-untyped-def]
    ok = await client.post(
        "/api/v1/models/detect-protocol",
        json={"base_url": "https://gw/v1", "secret_value": "sk-x"},
    )
    assert ok.status_code == 200 and ok.json()["protocol"] == "openai"
    # a failed probe degrades to "unknown" (never 500), so the agent page asks.
    deg = await client.post(
        "/api/v1/models/detect-protocol",
        json={"base_url": "https://gw/v1", "secret_value": "bad"},
    )
    assert deg.status_code == 200 and deg.json()["protocol"] == "unknown"


async def test_requires_token(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post(
        "/api/v1/models/list-models", json={"provider": "openai"}, headers={"X-Coffer-Token": "x"}
    )
    assert r.status_code == 401
