"""A title on every resource, and a name that some kinds fix.

spec resource-framework "Carry an optional editable title on every resource" and
"Treat a resource's name as a mutable label"; spec mcp-gateway "Manage MCP
servers as resources" for the 24-character cap on a new server name.

The kinds are real where the rule belongs to the kind: ``mcp_server`` is built by
its own ``make_mcp_kind`` (with no live session to evict), so the fixed name and
the name cap tested here are the production declarations, not a restatement.
``plain`` is a synthetic renamable kind with a reach, standing for every kind
whose name is not fixed.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Kind
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router


class _PlainConfig(BaseModel):
    foo: int = 1


_SERVER_CONFIG: dict[str, Any] = {
    "transport": {"type": "http", "url": "https://example.invalid/mcp"},
}


async def _app(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    kinds = {
        "plain": Kind(
            name="plain", display_name="Plain", config_schema=_PlainConfig, supports_scope=True
        ),
        "mcp_server": make_mcp_kind({}),
    }
    svc = ResourceService(
        kinds=kinds,
        repo=SqlAlchemyResourceRepo(sm),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(resource_router)
    app.dependency_overrides[get_resource_service] = lambda: svc
    set_active_token("test-token")
    client = AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": "test-token"}
    )
    return client, svc, engine


def _audit(tmp_path) -> list[tuple[str, str]]:
    """Every audit row, as (event_type, name-at-the-time)."""
    with sqlite3.connect(tmp_path / "c.db") as db:
        return list(db.execute("SELECT event_type, resource_name FROM audit_log ORDER BY id"))


def _updates(tmp_path) -> list[str]:
    with sqlite3.connect(tmp_path / "c.db") as db:
        return [
            row[0]
            for row in db.execute(
                "SELECT details_json FROM audit_log WHERE event_type = 'resource_updated'"
            )
        ]


# --- title ---------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="resource-framework", scenario="a title is shown in place of the name")
async def test_a_title_is_carried_beside_the_name_and_changes_nothing_else(tmp_path):
    c, _svc, engine = await _app(tmp_path)
    async with c:
        created = (
            await c.post(
                "/api/v1/resources",
                json={"kind": "plain", "name": "search", "config": {"foo": 1}},
            )
        ).json()
        uid = created["uid"]
        assert created["title"] is None
        await c.put(f"/api/v1/resources/{uid}/scope", json={"scope": {"agents": ["a1"]}})
        await c.post(f"/api/v1/resources/{uid}/disable")
        before = (await c.get(f"/api/v1/resources/{uid}")).json()

        r = await c.patch(f"/api/v1/resources/{uid}", json={"title": "Team search"})
        assert r.status_code == 200, r.text

        # The list and the single read carry both the name and the title, so a
        # surface can show the title where it showed the name.
        listed = (await c.get("/api/v1/resources", params={"kind": "plain"})).json()["resources"]
        assert [(row["name"], row["title"]) for row in listed] == [("search", "Team search")]
        shown = (await c.get(f"/api/v1/resources/{uid}")).json()
        assert (shown["name"], shown["title"]) == ("search", "Team search")
        # Name, uid, reach and enabled state are unchanged.
        for field in ("uid", "name", "scope", "enabled", "config", "description"):
            assert shown[field] == before[field], field

    # Audited as an update, naming what moved.
    assert _audit(tmp_path)[-1] == ("resource_updated", "search")
    assert '"title"' in _updates(tmp_path)[-1] and "Team search" in _updates(tmp_path)[-1]
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="resource-framework", scenario="an over-long title is refused")
async def test_an_over_long_title_is_refused_and_an_empty_one_clears(tmp_path):
    c, svc, engine = await _app(tmp_path)
    async with c:
        uid = (
            await c.post(
                "/api/v1/resources",
                json={"kind": "plain", "name": "search", "config": {}, "title": "Team search"},
            )
        ).json()["uid"]
        events_before = len(_audit(tmp_path))

        too_long = await c.patch(f"/api/v1/resources/{uid}", json={"title": "x" * 81})
        assert too_long.status_code == 422, too_long.text
        assert (await c.get(f"/api/v1/resources/{uid}")).json()["title"] == "Team search"
        assert len(_audit(tmp_path)) == events_before

        # Exactly 80 is allowed.
        assert (
            await c.patch(f"/api/v1/resources/{uid}", json={"title": "y" * 80})
        ).status_code == 200

        cleared = await c.patch(f"/api/v1/resources/{uid}", json={"title": ""})
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["title"] is None
        assert (await c.get(f"/api/v1/resources/{uid}")).json()["title"] is None

    # The same cap holds for a caller that is not the HTTP body model — the
    # sync applier, the CLI — because the service checks it too.
    from coffer.domain.errors import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="80"):
        await svc.set_title(uid, "z" * 81, "test")
    assert (await svc.get(uid)).title is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_title_edit_alone_does_not_rewrite_the_config(tmp_path):
    """A title-only PATCH writes one column: no config re-validation, no config
    audit entry with identical before and after, no rename."""
    c, _svc, engine = await _app(tmp_path)
    async with c:
        uid = (
            await c.post("/api/v1/resources", json={"kind": "plain", "name": "s", "config": {}})
        ).json()["uid"]
        await c.patch(f"/api/v1/resources/{uid}", json={"title": "T"})
        # Re-sending the same title records nothing.
        await c.patch(f"/api/v1/resources/{uid}", json={"title": "T"})
    updates = _updates(tmp_path)
    assert len(updates) == 1
    assert '"before"' in updates[0] and '"config"' not in updates[0]
    assert all(event != "resource_renamed" for event, _ in _audit(tmp_path))
    await engine.dispose()


# --- a fixed name --------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="resource-framework", scenario="a fixed name refuses a rename")
async def test_an_mcp_server_name_change_is_refused_before_anything_is_written(tmp_path):
    c, _svc, engine = await _app(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "search",
                "config": _SERVER_CONFIG,
                "description": "as registered",
            },
        )
        assert created.status_code == 201, created.text
        uid = created.json()["uid"]
        trail_before = _audit(tmp_path)

        # A rename alone, and a rename carried beside another edit: both refused,
        # and the other edit is not written either.
        for body in (
            {"name": "search-v2"},
            {"name": "search-v2", "description": "changed", "title": "Search"},
        ):
            r = await c.patch(f"/api/v1/resources/{uid}", json=body)
            assert r.status_code == 409, r.text
            error = r.json()["error"]
            assert error["code"] == "NAME_IMMUTABLE"
            assert "delete it and register it again" in error["message"]
            assert "capability toggles" in error["message"] and "reach" in error["message"]

        after = (await c.get(f"/api/v1/resources/{uid}")).json()
        assert after["name"] == "search"
        assert after["description"] == "as registered"
        assert after["title"] is None
        assert _audit(tmp_path) == trail_before, "a refused rename audits nothing"

        # Submitting the name it already has is not a change.
        same = await c.patch(f"/api/v1/resources/{uid}", json={"name": "search"})
        assert same.status_code == 200, same.text

        # A title change on the same resource still succeeds.
        titled = await c.patch(f"/api/v1/resources/{uid}", json={"title": "Team search"})
        assert titled.status_code == 200, titled.text
        assert (titled.json()["name"], titled.json()["title"]) == ("search", "Team search")
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework", scenario="renaming a resource is an ordinary edit"
)
async def test_a_kind_whose_name_is_not_fixed_still_renames(tmp_path):
    """The fixed name is a declaration of two kinds, not a new rule for all."""
    c, _svc, engine = await _app(tmp_path)
    async with c:
        uid = (
            await c.post("/api/v1/resources", json={"kind": "plain", "name": "a", "config": {}})
        ).json()["uid"]
        r = await c.patch(f"/api/v1/resources/{uid}", json={"name": "b"})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "b"
        assert r.json()["uid"] == uid
    await engine.dispose()


# --- the 24-character cap on a new MCP server name -----------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a server name longer than 24 characters is refused at registration",
)
async def test_a_new_server_name_over_24_characters_is_refused(tmp_path):
    c, svc, engine = await _app(tmp_path)
    # A server registered before the cap: it arrives the way the only such row
    # can still arrive — with the identity another machine already gave it —
    # and the rule for NEW names does not apply to it.
    earlier = await svc.register(
        "mcp_server", "a" * 30, _SERVER_CONFIG, "sync", uid="0123456789abcdef0123456789abcdef"
    )
    async with c:
        refused = await c.post(
            "/api/v1/resources",
            json={"kind": "mcp_server", "name": "b" * 25, "config": _SERVER_CONFIG},
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "CONFIG_INVALID"
        assert "24" in refused.json()["error"]["message"]

        accepted = await c.post(
            "/api/v1/resources",
            json={"kind": "mcp_server", "name": "c" * 24, "config": _SERVER_CONFIG},
        )
        assert accepted.status_code == 201, accepted.text

        names = sorted(
            row["name"]
            for row in (await c.get("/api/v1/resources", params={"kind": "mcp_server"})).json()[
                "resources"
            ]
        )
        # Nothing was persisted for the refused name; the earlier server keeps
        # its 30-character name and still loads.
        assert names == ["a" * 30, "c" * 24]
        loaded = (await c.get(f"/api/v1/resources/{earlier.uid}")).json()
        assert loaded["name"] == "a" * 30
    await engine.dispose()
