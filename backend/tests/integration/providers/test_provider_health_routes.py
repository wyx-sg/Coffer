"""The kept health verdicts over HTTP, on a real ``derived.db`` (no network)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.provider.health import ProviderHealthService
from coffer.application.provider.introspection import ModelIntrospectionService
from coffer.application.provider.ports import ModelList
from coffer.domain.errors import ResourceNotFound
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource
from coffer.infrastructure.persistence.derived_db import open_derived_db
from coffer.infrastructure.provider.health_repo import ProviderHealthRepo
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.model_routes import router as model_router
from coffer.surfaces.http.provider_dependencies import (
    set_introspection_service,
    set_provider_service,
)
from coffer.surfaces.http.provider_health_routes import router as health_router
from coffer.surfaces.http.provider_health_routes import set_provider_health_service
from tests.unit.application._attention_fakes import resource

_TOKEN = "t-health"
_URLS = {"refused": "https://refused/v1", "fine": "https://fine/v1"}


def _connection(uid: str) -> Resource:
    cfg = ProviderConfig(protocol="openai", base_url=_URLS[uid], secret_ref=f"ref-{uid}")
    return resource(uid, "provider", cfg.model_dump(mode="json"))


class _Port:
    """The endpoints: one refuses its key, one answers; a typed key always works."""

    async def list_models(self, *, provider, base_url, api_key):  # type: ignore[no-untyped-def]
        if base_url == _URLS["refused"] and api_key != "typed":
            raise RuntimeError("Error code: 401 - invalid api key")
        return ["m1"]

    async def test_chat(self, **_kw):  # type: ignore[no-untyped-def]
        return None


class _Providers:
    _boundary = None

    def __init__(self) -> None:
        self.rows = {uid: _connection(uid) for uid in _URLS}

    async def list(self) -> list[Resource]:
        return list(self.rows.values())

    async def get(self, uid: str) -> Resource:
        if uid not in self.rows:
            raise ResourceNotFound(f"connection {uid} not found")
        return self.rows[uid]


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, ProviderHealthService]]:
    engine, sm = await open_derived_db(tmp_path / "derived.db")
    introspection = ModelIntrospectionService(_Port(), lambda ref: f"key-{ref}")
    providers = _Providers()

    async def list_models(protocol: str, base_url: str | None, ref: str | None) -> ModelList:
        return await introspection.list_models(provider=protocol, base_url=base_url, secret_ref=ref)

    async def authorize(_row: Resource, _cfg: ProviderConfig) -> None:
        return None

    service = ProviderHealthService(
        store=ProviderHealthRepo(sm),
        connections=providers,
        list_models=list_models,
        authorize=authorize,
        background=False,
    )
    set_provider_health_service(service)
    set_introspection_service(introspection)
    set_provider_service(providers)  # type: ignore[arg-type]
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(model_router)
    err_handlers.register(app)
    set_active_token(_TOKEN)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    ) as c:
        yield c, service
    set_active_token(None)
    set_provider_health_service(None)
    await engine.dispose()


async def _verdicts(c: AsyncClient) -> dict[str, str]:
    r = await c.get("/api/v1/providers/health")
    assert r.status_code == 200
    return {row["uid"]: row["status"] for row in r.json()["connections"]}


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a connection that never opened is marked in the list"
)
async def test_a_sweep_keeps_each_verdict_and_the_list_reads_it_back(client) -> None:  # type: ignore[no-untyped-def]
    c, service = client
    assert await _verdicts(c) == {}
    await service.check_all()
    assert await _verdicts(c) == {"fine": "reachable", "refused": "key_rejected"}
    [row] = [
        r
        for r in (await c.get("/api/v1/providers/health")).json()["connections"]
        if r["uid"] == "refused"
    ]
    assert row["source"] == "check"
    assert "401" in row["message"]


async def test_check_answers_the_verdict_and_404s_an_unknown_connection(client) -> None:  # type: ignore[no-untyped-def]
    c, _ = client
    r = await c.post("/api/v1/providers/refused/check")
    assert r.status_code == 200
    assert r.json()["health"]["status"] == "key_rejected"
    assert (await c.post("/api/v1/providers/nope/check")).status_code == 404


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a listing made with a typed key says nothing about the saved connection",
)
async def test_only_the_connections_own_listing_is_kept(client) -> None:  # type: ignore[no-untyped-def]
    c, _ = client
    own = {
        "provider": "openai",
        "base_url": _URLS["refused"],
        "secret_ref": "ref-refused",
        "connection_uid": "refused",
    }
    r = await c.post("/api/v1/models/list-models", json=own)
    assert r.status_code == 200
    assert await _verdicts(c) == {"refused": "key_rejected"}

    # A typed key answers, but it is not the saved connection's key.
    typed = {**own, "secret_ref": None, "secret_value": "typed"}
    assert (await c.post("/api/v1/models/list-models", json=typed)).json()["reachable"]
    # A draft URL is not the saved connection either.
    draft = {**own, "base_url": _URLS["fine"]}
    assert (await c.post("/api/v1/models/list-models", json=draft)).status_code in (200, 422)
    assert await _verdicts(c) == {"refused": "key_rejected"}
