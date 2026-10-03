"""resource-framework scenarios that are REST-only now that the CLI carries no
lifecycle verbs, reach or retention commands.

Specs: resource-framework "Address every resource by an immutable uid through one
kind-agnostic surface", "Carry a per-agent reach on every resource" and "Prune
each registered log table on its own retention period".
"""

from __future__ import annotations

import sqlite3

import pytest

from coffer.domain.resource import Kind
from tests.integration.surfaces.http.test_resource_title_and_fixed_name import (
    _app,
    _audit,
    _PlainConfig,
)
from tests.integration.surfaces.http.test_retention_routes import _client as _retention_client


def _bare_kind() -> Kind:
    """A kind that can be disabled by nobody, reaches no agent, carries no title."""
    return Kind(
        name="bare",
        display_name="Bare",
        config_schema=_PlainConfig,
        supports_scope=False,
        toggleable=False,
        titled=False,
    )


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework", scenario="every kind answers the same lifecycle routes"
)
async def test_every_kind_answers_the_same_lifecycle_routes(tmp_path):
    c, _svc, engine = await _app(tmp_path, extra_kinds={"bare": _bare_kind()})
    async with c:
        full = (
            await c.post("/api/v1/resources", json={"kind": "plain", "name": "a", "config": {}})
        ).json()["uid"]
        bare = (
            await c.post("/api/v1/resources", json={"kind": "bare", "name": "b", "config": {}})
        ).json()["uid"]

        # Both answer the read and the description update through the same routes.
        for uid in (full, bare):
            assert (await c.get(f"/api/v1/resources/{uid}")).status_code == 200
            patched = await c.patch(f"/api/v1/resources/{uid}", json={"description": "d"})
            assert patched.status_code == 200, patched.text
            assert patched.json()["description"] == "d"

        # The kind that supports none of reach, title or disabling refuses each.
        trail = _audit(tmp_path)
        scoped = await c.put(f"/api/v1/resources/{bare}/scope", json={"scope": {"agents": ["a1"]}})
        titled = await c.patch(f"/api/v1/resources/{bare}", json={"title": "T"})
        disabled = await c.post(f"/api/v1/resources/{bare}/disable")
        assert scoped.status_code >= 400, scoped.text
        assert titled.status_code == 422, titled.text
        assert disabled.status_code == 409, disabled.text
        shown = (await c.get(f"/api/v1/resources/{bare}")).json()
        assert (shown["scope"], shown["title"], shown["enabled"]) == (None, None, True)
        assert _audit(tmp_path) == trail

        # The first kind takes all three through the same routes, each audited.
        assert (
            await c.put(f"/api/v1/resources/{full}/scope", json={"scope": {"agents": ["a1"]}})
        ).status_code == 200
        assert (
            await c.patch(f"/api/v1/resources/{full}", json={"title": "Title"})
        ).status_code == 200
        off = await c.post(f"/api/v1/resources/{full}/disable")
        assert off.status_code == 200 and off.json()["enabled"] is False
    assert ("resource_disabled", "a") in _audit(tmp_path)
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="a resource's reach is written and read through the scope routes",
)
async def test_a_resources_reach_is_written_and_read_through_the_scope_routes(tmp_path):
    c, _svc, engine = await _app(tmp_path, extra_kinds={"bare": _bare_kind()})
    async with c:
        uid = (
            await c.post("/api/v1/resources", json={"kind": "plain", "name": "a", "config": {}})
        ).json()["uid"]
        bare = (
            await c.post("/api/v1/resources", json={"kind": "bare", "name": "b", "config": {}})
        ).json()["uid"]

        one = await c.put(f"/api/v1/resources/{uid}/scope", json={"scope": {"agents": ["a1"]}})
        assert one.status_code == 200, one.text
        read = (await c.get(f"/api/v1/resources/{uid}/scope")).json()
        assert read["scope"] == {"agents": ["a1"]}
        assert read["supports_scope"] is True

        every = await c.put(f"/api/v1/resources/{uid}/scope", json={"scope": None})
        assert every.status_code == 200, every.text
        assert (await c.get(f"/api/v1/resources/{uid}/scope")).json()["scope"] is None

        refused = await c.put(f"/api/v1/resources/{bare}/scope", json={"scope": {"agents": ["a1"]}})
        assert refused.status_code >= 400, refused.text
        assert (await c.get(f"/api/v1/resources/{bare}/scope")).json()["supports_scope"] is False
    with sqlite3.connect(tmp_path / "c.db") as db:
        events = [r[0] for r in db.execute("SELECT event_type FROM audit_log ORDER BY id")]
    assert events.count("resource_scope_updated") == 2
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework", scenario="set a retention period and prune now over REST"
)
async def test_a_retention_period_is_set_and_pruned_now_over_rest(tmp_path):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from coffer.infrastructure.persistence.engine import session_maker
    from coffer.infrastructure.persistence.models import AuditLogModel

    c, engine = await _retention_client(tmp_path)
    now = datetime.now(tz=UTC)
    async with session_maker(engine)() as s:
        for age in (1, 3, 10, 40):
            s.add(
                AuditLogModel(
                    timestamp=now - timedelta(days=age),
                    event_type="resource_created",
                    resource_kind="mcp_server",
                    resource_name=f"r{age}",
                    actor="user",
                    details_json=None,
                )
            )
        await s.commit()
    async with c:
        patched = await c.patch("/api/v1/retention/policies/audit_log", json={"retention_days": 7})
        assert patched.status_code == 200, patched.text
        pruned = await c.post("/api/v1/retention/prune", json={"table_name": "audit_log"})
        assert pruned.status_code == 200, pruned.text
        assert pruned.json()["tables"]["audit_log"] == 2
        policies = (await c.get("/api/v1/retention/policies")).json()["policies"]
        assert [p["retention_days"] for p in policies] == [7]
    async with session_maker(engine)() as s:
        named = select(AuditLogModel.resource_name).where(AuditLogModel.resource_name.is_not(None))
        assert sorted((await s.execute(named)).scalars().all()) == ["r1", "r3"]
        events = select(AuditLogModel.event_type)
        assert "retention_updated" in (await s.execute(events)).scalars().all()
    await engine.dispose()
