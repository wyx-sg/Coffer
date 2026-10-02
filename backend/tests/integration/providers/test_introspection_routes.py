"""HTTP contract tests for provider introspection routes (no network)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.provider.introspection import ModelIntrospectionService
from coffer.domain.provider.config import ProviderConfig
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.model_routes import router as model_router
from coffer.surfaces.http.provider_dependencies import (
    set_introspection_service,
    set_provider_service,
)

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


class _Row:
    def __init__(self, uid: str, name: str, cfg: ProviderConfig) -> None:
        self.uid = uid
        self.name = name
        self.config = cfg.model_dump(mode="json")


class _FakeProviders:
    """The saved connections the routes check a stored ref against."""

    _boundary = None

    async def list(self):  # type: ignore[no-untyped-def]
        return [
            _Row(
                "u1",
                "gw",
                ProviderConfig(protocol="openai", base_url="https://gw/v1", secret_ref="ok"),
            ),
            _Row(
                "u2",
                "bad",
                ProviderConfig(protocol="openai", base_url="https://gw/v1", secret_ref="bad-ref"),
            ),
        ]


@pytest_asyncio.fixture
async def client():  # type: ignore[no-untyped-def]
    set_introspection_service(
        ModelIntrospectionService(_FakePort(), lambda ref: {"ok": "k", "bad-ref": "bad"}[ref])
    )
    set_provider_service(_FakeProviders())  # type: ignore[arg-type]
    app = FastAPI()
    app.include_router(model_router)
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
        "/api/v1/models/list-models",
        json={"provider": "openai", "secret_ref": "ok", "base_url": "https://gw/v1"},
    )
    assert r.status_code == 200
    # Each id comes back with a modality GUESSED from its name, so the
    # connection's model table pre-fills a kind the user can correct.
    assert [{"id": m["id"], "modality": m["modality"]} for m in r.json()["models"]] == [
        {"id": "gpt-4o", "modality": "text"},
        {"id": "gpt-4o-mini", "modality": "text"},
        {"id": "text-embedding-3-small", "modality": "embedding"},
    ]
    assert r.json()["reachable"] is True


async def test_list_models_degrades(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/api/v1/models/list-models", json={"provider": "broken"})
    assert r.status_code == 200
    assert r.json()["models"] == []
    assert "connection refused" in r.json()["message"]
    assert r.json()["reachable"] is False


@pytest.mark.acceptance(spec="provider-switching", scenario="test a model connection")
async def test_test_connection_ok_and_fail(client) -> None:  # type: ignore[no-untyped-def]
    ok = await client.post(
        "/api/v1/models/test-connection",
        json={
            "provider": "openai",
            "model": "gpt-4o",
            "secret_ref": "ok",
            "base_url": "https://gw/v1",
        },
    )
    assert ok.status_code == 200 and ok.json()["ok"] is True
    bad = await client.post(
        "/api/v1/models/test-connection",
        json={
            "provider": "openai",
            "model": "gpt-4o",
            "secret_ref": "bad-ref",
            "base_url": "https://gw/v1",
        },
    )
    assert bad.status_code == 200 and bad.json()["ok"] is False


async def test_inline_secret_reaches_port(client) -> None:  # type: ignore[no-untyped-def]
    # An inline secret (no secret_ref) flows straight to the port: "bad"
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


async def test_requires_token(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post(
        "/api/v1/models/list-models", json={"provider": "openai"}, headers={"X-Coffer-Token": "x"}
    )
    assert r.status_code == 401


@pytest.mark.acceptance(
    spec="secret", scenario="a stored key goes only to the endpoint of the connection that holds it"
)
async def test_a_stored_ref_is_not_sent_to_a_foreign_url(client) -> None:  # type: ignore[no-untyped-def]
    # A ref some saved connection holds, paired with a URL it was never approved
    # for, is refused on both routes — nothing is decrypted or sent.
    for path, extra in (
        ("list-models", {"provider": "openai"}),
        ("test-connection", {"provider": "openai", "model": "gpt-4o"}),
    ):
        r = await client.post(
            f"/api/v1/models/{path}",
            json={**extra, "secret_ref": "ok", "base_url": "https://evil.example/v1"},
        )
        assert r.status_code == 422, path
        assert r.json()["error"]["code"] == "CONFIG_INVALID"


@pytest.mark.acceptance(
    spec="secret", scenario="a stored key goes only to the endpoint of the connection that holds it"
)
async def test_a_ref_no_connection_holds_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post(
        "/api/v1/models/list-models",
        json={"provider": "openai", "secret_ref": "mcp/x/token", "base_url": "https://gw/v1"},
    )
    assert r.status_code == 422
