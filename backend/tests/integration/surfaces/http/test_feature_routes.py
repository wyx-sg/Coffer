"""/api/v1/daemon/features, the status fields, and the ``require_feature`` gate.

Every test runs under a throwaway HOME, so ``daemon-config.json`` is written
into ``tmp_path`` and never into the developer's own ``~/.coffer``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.features import FeatureService
from coffer.infrastructure.daemon import config as daemon_config
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http import feature_dependencies
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.daemon_routes import router as daemon_router
from coffer.surfaces.http.feature_dependencies import (
    build_feature_service,
    require_feature,
    set_feature_service,
)
from coffer.surfaces.http.feature_routes import router as feature_router

_TOKEN = "t"


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    h = tmp_path / "home"
    (h / ".coffer").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.delenv(daemon_config.FEATURES_ENV, raising=False)
    prior = feature_dependencies._feature_service
    set_active_token(_TOKEN)
    yield h
    set_active_token(None)
    feature_dependencies._feature_service = prior


def _gated_router() -> APIRouter:
    r = APIRouter(prefix="/api/v1/knowledge", dependencies=[Depends(require_feature("knowledge"))])

    @r.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "yes"}

    return r


def _app(svc: FeatureService | None) -> FastAPI:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(daemon_router)
    app.include_router(feature_router)
    app.include_router(_gated_router())
    if svc is not None:
        set_feature_service(svc)
    else:
        feature_dependencies._feature_service = None
    return app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = _app(build_feature_service())
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    ) as c:
        yield c


def _config(home: Path) -> dict[str, object]:
    return json.loads((home / ".coffer" / "daemon-config.json").read_text())  # type: ignore[no-any-return]


@pytest.mark.acceptance(
    spec="experimental-features", scenario="the registry names the three features"
)
async def test_the_features_list_names_exactly_the_three_with_state_and_source(
    client: AsyncClient,
) -> None:
    r = await client.get("/api/v1/daemon/features")
    assert r.status_code == 200
    assert r.json() == {
        "channel": "dev",
        "features": [
            {"key": "vault_sync", "enabled": True, "source": "channel"},
            {"key": "knowledge", "enabled": True, "source": "channel"},
            {"key": "memory", "enabled": True, "source": "channel"},
        ],
    }


async def test_the_features_routes_need_the_token(client: AsyncClient) -> None:
    assert (
        await client.get("/api/v1/daemon/features", headers={"X-Coffer-Token": ""})
    ).status_code == 401
    r = await client.put(
        "/api/v1/daemon/features/memory",
        json={"enabled": False},
        headers={"X-Coffer-Token": "wrong"},
    )
    assert r.status_code == 401


@pytest.mark.acceptance(
    spec="experimental-features", scenario="a source build reports the dev channel"
)
async def test_status_reports_the_dev_channel_and_every_feature_unauthenticated(
    client: AsyncClient,
) -> None:
    r = await client.get("/api/v1/daemon/status", headers={"X-Coffer-Token": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["channel"] == "dev"
    assert body["features"] == {"vault_sync": True, "knowledge": True, "memory": True}


async def test_put_switches_a_feature_writes_the_config_and_status_follows(
    client: AsyncClient, home: Path
) -> None:
    r = await client.put("/api/v1/daemon/features/knowledge", json={"enabled": False})
    assert r.status_code == 200
    assert r.json() == {"key": "knowledge", "enabled": False, "source": "setting"}
    assert _config(home) == {"features": {"knowledge": False}}
    status = (await client.get("/api/v1/daemon/status")).json()
    assert status["features"]["knowledge"] is False


async def test_put_an_unknown_key_answers_feature_unknown(client: AsyncClient, home: Path) -> None:
    r = await client.put("/api/v1/daemon/features/workflow", json={"enabled": True})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "FEATURE_UNKNOWN"
    assert not (home / ".coffer" / "daemon-config.json").exists()


async def test_put_without_a_boolean_is_refused(client: AsyncClient) -> None:
    r = await client.put("/api/v1/daemon/features/memory", json={})
    assert r.status_code == 422


@pytest.mark.acceptance(
    spec="experimental-features", scenario="a pinned feature cannot be switched"
)
async def test_a_pinned_feature_answers_409_and_stays_off(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    monkeypatch.setenv(daemon_config.FEATURES_ENV, "knowledge=off")
    app = _app(build_feature_service())
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    ) as c:
        r = await c.put("/api/v1/daemon/features/knowledge", json={"enabled": True})
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "FEATURE_PINNED"
        assert r.json()["error"]["details"] == {"feature": "knowledge"}
        listed = (await c.get("/api/v1/daemon/features")).json()["features"]
        assert {"key": "knowledge", "enabled": False, "source": "pin"} in listed
    assert not (home / ".coffer" / "daemon-config.json").exists()


async def test_the_gate_answers_feature_disabled_and_opens_without_a_restart(
    client: AsyncClient,
) -> None:
    assert (await client.get("/api/v1/knowledge/ping")).json() == {"pong": "yes"}

    await client.put("/api/v1/daemon/features/knowledge", json={"enabled": False})
    r = await client.get("/api/v1/knowledge/ping")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "FEATURE_DISABLED"
    assert r.json()["error"]["details"] == {"feature": "knowledge"}

    await client.put("/api/v1/daemon/features/knowledge", json={"enabled": True})
    assert (await client.get("/api/v1/knowledge/ping")).status_code == 200


def test_require_feature_refuses_an_unregistered_key_at_wiring_time() -> None:
    from coffer.domain.features import FeatureUnknown

    with pytest.raises(FeatureUnknown):
        require_feature("workflow")


async def test_status_answers_on_an_app_that_published_no_service(home: Path) -> None:
    """A bare app (no create_app) still reports what this machine would decide."""
    daemon_config.write_feature_setting("memory", False)
    app = _app(None)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        body = (await c.get("/api/v1/daemon/status")).json()
    assert body["features"] == {"vault_sync": True, "knowledge": True, "memory": False}


async def test_create_app_publishes_the_service_on_app_state(home: Path) -> None:
    from coffer.surfaces.http.app import create_app

    daemon_config.write_feature_setting("vault_sync", False)
    app = create_app()
    svc = app.state.feature_service
    assert isinstance(svc, FeatureService)
    assert feature_dependencies.get_feature_service() is svc
    assert svc.state("vault_sync").source == "setting"
    async with AsyncClient(
        transport=ASGITransport(app),
        base_url="http://127.0.0.1",
        headers={"X-Coffer-Token": _TOKEN},
    ) as c:
        r = await c.get("/api/v1/daemon/features")
    assert r.status_code == 200
    assert r.json()["features"][0] == {"key": "vault_sync", "enabled": False, "source": "setting"}
