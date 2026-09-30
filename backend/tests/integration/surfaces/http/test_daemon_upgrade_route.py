"""``GET /api/v1/daemon/upgrade`` (spec daemon "Hand an upgrade of Coffer to an agent")."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import coffer
from coffer.surfaces.http import daemon_upgrade_routes
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
