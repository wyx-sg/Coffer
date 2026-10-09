"""A free-text name on the kinds that take one, and a name that some kinds fix.

spec resource-framework "Name a provider or a channel with free text" and
"Treat a resource's name as a mutable label"; spec mcp-gateway "Manage MCP
servers as resources" for the 24-character cap on a new server name.

The kinds are real where the rule belongs to the kind: ``mcp_server`` is built by
its own ``make_mcp_kind`` (with no live session to evict), so the fixed name and
the name cap tested here are the production declarations, not a restatement.
``plain`` is a synthetic renamable kind with a reach, standing for every kind
whose name is not fixed; ``named`` is one whose name is free text, as a
provider's and a channel's are.
"""

from __future__ import annotations

import json
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
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_repository
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router
from tests.support.vault_stores import make_resource_repo


class _PlainConfig(BaseModel):
    foo: int = 1


_SERVER_CONFIG: dict[str, Any] = {
    "transport": {"type": "http", "url": "https://example.invalid/mcp"},
}


async def _app(tmp_path, extra_kinds: dict[str, Kind] | None = None):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    kinds = {
        "plain": Kind(
            name="plain", display_name="Plain", config_schema=_PlainConfig, supports_scope=True
        ),
        "named": Kind(
            name="named", display_name="Named", config_schema=_PlainConfig, free_name=True
        ),
        "mcp_server": make_mcp_kind({}),
        **(extra_kinds or {}),
    }
    svc = ResourceService(
        kinds=kinds,
        repo=make_resource_repo(kinds),
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


# --- a free-text name ------------------------------------------------------------


def _file_of(uid: str) -> str | None:
    found = [p for p in vault_repository().tree("HEAD", "resources/named") if uid in p]
    return found[0] if found else None


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework", scenario="a free-text name is stored as typed and renamed in place"
)
async def test_a_free_text_name_is_stored_trimmed_and_renamed_without_moving_its_file(tmp_path):
    c, _svc, engine = await _app(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources", json={"kind": "named", "name": "  团队 Search ✨ ", "config": {}}
        )
        assert created.status_code == 201, created.text
        uid = created.json()["uid"]
        assert created.json()["name"] == "团队 Search ✨"
        assert "title" not in created.json()
        assert _file_of(uid) == f"resources/named/{uid}.json"

        renamed = await c.patch(f"/api/v1/resources/{uid}", json={"name": "Team search"})
        assert renamed.status_code == 200, renamed.text
        assert (await c.get(f"/api/v1/resources/{uid}")).json()["name"] == "Team search"
        assert _file_of(uid) == f"resources/named/{uid}.json"
    assert _audit(tmp_path)[-1] == ("resource_renamed", "Team search")
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework", scenario="a name that breaks the rule is refused"
)
async def test_a_free_name_outside_the_rule_and_display_text_on_a_slug_kind_are_refused(tmp_path):
    c, _svc, engine = await _app(tmp_path)
    async with c:
        for name in ("x" * 81, "two\nlines", "-flag", "   "):
            r = await c.post(
                "/api/v1/resources", json={"kind": "named", "name": name, "config": {}}
            )
            assert r.status_code == 422, (name, r.text)
        slug = await c.post(
            "/api/v1/resources", json={"kind": "plain", "name": "Team search", "config": {}}
        )
        assert slug.status_code == 422, slug.text
        listed = (await c.get("/api/v1/resources")).json()["resources"]
        assert listed == []
    assert _audit(tmp_path) == []
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework", scenario="a kind that is not free-text refuses a name with a space"
)
async def test_a_kind_that_is_not_free_text_refuses_a_name_with_a_space(tmp_path):
    c, _svc, engine = await _app(tmp_path)
    async with c:
        for kind in ("mcp_server", "plain"):
            config = _SERVER_CONFIG if kind == "mcp_server" else {}
            r = await c.post(
                "/api/v1/resources", json={"kind": kind, "name": "My Server", "config": config}
            )
            assert r.status_code == 422, (kind, r.text)
            assert r.json()["error"]["code"] == "CONFIG_INVALID"
        assert (await c.get("/api/v1/resources")).json()["resources"] == []
    assert _audit(tmp_path) == []
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework", scenario="a rename that only changes case is allowed"
)
@pytest.mark.acceptance(spec="resource-framework", scenario="a rename does not move the file")
async def test_a_case_only_rename_is_audited_and_leaves_the_file_where_it_is(tmp_path):
    c, _svc, engine = await _app(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources", json={"kind": "named", "name": "work", "config": {}}
        )
        uid = created.json()["uid"]
        assert _file_of(uid) == f"resources/named/{uid}.json"

        r = await c.patch(f"/api/v1/resources/{uid}", json={"name": "Work"})
        assert r.status_code == 200, r.text
        assert (r.json()["uid"], r.json()["name"]) == (uid, "Work")
        assert _file_of(uid) == f"resources/named/{uid}.json"
        doc = json.loads((vault_root() / f"resources/named/{uid}.json").read_text())
        assert doc["name"] == "Work"
    assert _audit(tmp_path)[-1] == ("resource_renamed", "Work")
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework", scenario="two free-text names clash ignoring case"
)
async def test_free_text_names_clash_ignoring_case_but_a_resource_may_recase_its_own(tmp_path):
    c, _svc, engine = await _app(tmp_path)
    async with c:
        work = await c.post(
            "/api/v1/resources", json={"kind": "named", "name": "Work", "config": {}}
        )
        home = await c.post(
            "/api/v1/resources", json={"kind": "named", "name": "Home", "config": {}}
        )
        clash = await c.post(
            "/api/v1/resources", json={"kind": "named", "name": "work", "config": {}}
        )
        assert clash.status_code == 409, clash.text
        taken = await c.patch(f"/api/v1/resources/{home.json()['uid']}", json={"name": "WORK"})
        assert taken.status_code == 409, taken.text
        recased = await c.patch(f"/api/v1/resources/{work.json()['uid']}", json={"name": "WORK"})
        assert recased.status_code == 200, recased.text
        assert recased.json()["name"] == "WORK"
    await engine.dispose()


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
            {"name": "search-v2", "description": "changed"},
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
        assert _audit(tmp_path) == trail_before, "a refused rename audits nothing"

        # Submitting the name it already has is not a change.
        same = await c.patch(f"/api/v1/resources/{uid}", json={"name": "search"})
        assert same.status_code == 200, same.text
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


# --- the reserved name -----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a server cannot take the name of Coffer's own gateway"
)
async def test_a_server_cannot_be_named_coffer(tmp_path):
    c, _svc, engine = await _app(tmp_path)
    async with c:
        refused = await c.post(
            "/api/v1/resources",
            json={"kind": "mcp_server", "name": "coffer", "config": _SERVER_CONFIG},
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "CONFIG_INVALID"
        assert "reserved" in refused.json()["error"]["message"]
    await engine.dispose()


# --- the 24-character cap on a new MCP server name -----------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a server name longer than 24 characters is refused at registration",
)
async def test_a_new_server_name_over_24_characters_is_refused(tmp_path):
    c, _svc, engine = await _app(tmp_path)
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
        # Nothing was persisted for the refused name.
        assert names == ["c" * 24]
    await engine.dispose()
