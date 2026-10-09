"""``GET /api/v1/daemon/upgrade`` (spec daemon "Hand an upgrade of Coffer to an agent")."""

from __future__ import annotations

import pathlib

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import coffer
from coffer.infrastructure.daemon import release_check
from coffer.surfaces.http import daemon_upgrade_routes, release_check_wiring
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token


async def test_the_upgrade_route_hands_over_the_prompt() -> None:
    set_active_token("t")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(daemon_upgrade_routes.router)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": "t"}
    ) as c:
        r = await c.get("/api/v1/daemon/upgrade")
        refused = await c.get("/api/v1/daemon/upgrade", headers={"X-Coffer-Token": "no"})
    assert r.status_code == 200
    body = r.json()
    # The test run is a source run.
    assert body["install_method"] == "source"
    assert f"Coffer {coffer.__version__}" in body["handoff"]["prompt"]
    assert refused.status_code == 401


@pytest.mark.acceptance(
    spec="daemon", scenario="the daemon reports a newer release of its binaries"
)
async def test_a_binaries_daemon_reports_the_newer_release_its_check_found(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release_check, "config_path", lambda: tmp_path / "daemon-config.json")

    async def latest() -> release_check.Release:
        return release_check.Release(
            version="0.4.0",
            tag="v0.4.0",
            notes="- faster",
            published_at="2026-10-01T00:00:00Z",
            url="https://github.com/wyx-sg/Coffer/releases/tag/v0.4.0",
        )

    check = release_check.ReleaseCheck(
        running="0.3.0", applies=True, fetch=latest, pinned_off=lambda: False
    )
    release_check_wiring.set_release_check(check)
    set_active_token("t")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(daemon_upgrade_routes.router)
    try:
        async with AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": "t"}
        ) as c:
            before = (await c.get("/api/v1/daemon/upgrade")).json()
            checked = (await c.post("/api/v1/daemon/upgrade/check")).json()
            off = (await c.put("/api/v1/daemon/upgrade/auto-check", json={"enabled": False})).json()
    finally:
        release_check_wiring.set_release_check(None)
    assert before["checks"] is True and before["available"] is None
    assert checked["available"]["version"] == "0.4.0"
    assert checked["available"]["notes"] == "- faster"
    assert checked["checked_at"] is not None
    assert off["auto_check"] is False
    assert release_check.read_check_setting() is False


@pytest.mark.acceptance(spec="daemon", scenario="the app's daemon leaves checking to the app")
async def test_a_daemon_that_does_not_run_from_the_binaries_never_fetches() -> None:
    fetched: list[bool] = []

    async def latest() -> release_check.Release:
        fetched.append(True)
        raise AssertionError("must not fetch")

    check = release_check.ReleaseCheck(running="0.3.0", applies=False, fetch=latest)
    release_check_wiring.set_release_check(check)
    set_active_token("t")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(daemon_upgrade_routes.router)
    try:
        async with AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": "t"}
        ) as c:
            body = (await c.post("/api/v1/daemon/upgrade/check")).json()
    finally:
        release_check_wiring.set_release_check(None)
    assert body["checks"] is False and body["available"] is None
    assert fetched == []
