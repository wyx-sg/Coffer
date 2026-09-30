"""``PUT`` / ``DELETE /api/v1/attention/ignored/{key}`` over a real database:
an ignored informational item leaves ``items`` and ``counts_by_kind`` (which
the sidebar's badges and the menu bar count) and is listed under ``ignored``;
the choice is kept in ``attention_ignores`` and audited; a broken item cannot
be ignored."""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from coffer.application.attention import (
    AttentionAction,
    AttentionItem,
    AttentionService,
    Severity,
)
from coffer.application.audit_service import AuditService
from coffer.infrastructure.persistence.attention_ignore_repo import SqlAlchemyAttentionIgnoreRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.http import errors as http_errors
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.reconcile_dependencies import set_attention_service
from coffer.surfaces.http.reconcile_routes import attention_router

pytestmark = pytest.mark.asyncio

_TOKEN = "test-token-attention"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "ui"}

_CODEX = AttentionItem(
    kind="agent",
    uid="a-codex",
    title="Codex",
    reason_code="agent_not_connected",
    reason="It is not connected to Coffer.",
    severity=Severity.INFO,
    action=AttentionAction("connect", "POST", "/api/v1/agents/a-codex/coffer-connection"),
)
_GITHUB = AttentionItem(
    kind="mcp_server",
    uid="m-github",
    title="github",
    reason_code="mcp_failing",
    reason="Its last connection test failed.",
    severity=Severity.ERROR,
    action=AttentionAction("test", "POST", "/api/v1/mcp/m-github/test"),
)


class _Source:
    name = "fake"
    feature: str | None = None

    async def items(self) -> Sequence[AttentionItem]:
        return [_CODEX, _GITHUB]


@dataclass
class _Rig:
    client: AsyncClient
    engine: object

    async def audit_events(self) -> list[tuple[str, str]]:
        async with self.engine.connect() as conn:  # type: ignore[attr-defined]
            rows = await conn.execute(text("SELECT event_type, actor FROM audit_log ORDER BY id"))
            return [(r[0], r[1]) for r in rows]


@pytest_asyncio.fixture
async def rig(tmp_path: pathlib.Path) -> AsyncIterator[_Rig]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    service = AttentionService(
        [_Source()],
        feature_enabled=lambda _k: True,
        ignores=SqlAlchemyAttentionIgnoreRepo(sm),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )
    set_attention_service(service)
    set_active_token(_TOKEN)
    app = FastAPI()
    http_errors.register(app)
    app.include_router(attention_router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://127.0.0.1", headers=_HEADERS
    ) as client:
        yield _Rig(client, engine)
    set_attention_service(None)
    await engine.dispose()


@pytest.mark.acceptance(
    spec="web-ui", scenario="an ignored agent leaves needs you and is counted under it"
)
async def test_ignoring_an_unconnected_agent_moves_it_out_of_items_and_counts(rig: _Rig) -> None:
    before = (await rig.client.get("/api/v1/attention")).json()
    codex = next(i for i in before["items"] if i["uid"] == "a-codex")
    assert codex["key"] == "agent:a-codex:agent_not_connected" and codex["ignorable"] is True
    assert before["counts_by_kind"] == {"mcp_server": 1, "agent": 1}
    assert before["ignored"] == []

    r = await rig.client.put(f"/api/v1/attention/ignored/{codex['key']}")
    assert r.status_code == 204, r.text
    # Ignoring again changes nothing and audits nothing.
    assert (await rig.client.put(f"/api/v1/attention/ignored/{codex['key']}")).status_code == 204

    after = (await rig.client.get("/api/v1/attention")).json()
    assert [i["uid"] for i in after["items"]] == ["m-github"]
    assert after["counts_by_kind"] == {"mcp_server": 1}
    assert [i["uid"] for i in after["ignored"]] == ["a-codex"]

    r = await rig.client.delete(f"/api/v1/attention/ignored/{codex['key']}")
    assert r.status_code == 204
    back = (await rig.client.get("/api/v1/attention")).json()
    assert {i["uid"] for i in back["items"]} == {"m-github", "a-codex"}
    assert back["ignored"] == []

    assert await rig.audit_events() == [("attention_ignored", "ui"), ("attention_unignored", "ui")]


async def test_a_broken_or_unknown_item_cannot_be_ignored(rig: _Rig) -> None:
    for key in ("mcp_server:m-github:mcp_failing", "agent:nobody:agent_not_connected"):
        r = await rig.client.put(f"/api/v1/attention/ignored/{key}")
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "ATTENTION_NOT_IGNORABLE"
    body = (await rig.client.get("/api/v1/attention")).json()
    assert len(body["items"]) == 2 and body["ignored"] == []
    # Stopping to ignore what is not ignored is a no-op, not an error.
    r = await rig.client.delete("/api/v1/attention/ignored/agent:nobody:agent_not_connected")
    assert r.status_code == 204
    assert await rig.audit_events() == []
