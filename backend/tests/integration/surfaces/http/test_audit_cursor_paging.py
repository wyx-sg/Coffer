"""GET /api/v1/audit pages by an opaque cursor (spec resource-framework "Page
growing lists by an opaque cursor").

The rows are written straight through the real SQLite repo with chosen
timestamps — two of them identical — so the keyset's tie-break on the row id is
under test as well as the timestamp order. The route is served by a small app
holding only the audit router and the real error handlers, so a refused cursor
comes back in the same envelope the daemon answers with.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEntry
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.audit_routes import router as audit_router
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_audit_service, get_resource_service

_TOKEN = "test-token-audit-cursor"
_T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


class _Env:
    def __init__(self, client: httpx.AsyncClient, repo: SqlAlchemyAuditRepo) -> None:
        self.client = client
        self.repo = repo

    async def record(self, event_type: str, at: datetime, kind: str = "fake_kind") -> None:
        await self.repo.insert(
            AuditEntry(
                id=None,
                timestamp=at,
                event_type=event_type,
                resource_id=None,
                resource_kind=kind,
                resource_name="probe",
                actor="api",
                details={},
            )
        )

    async def read(self, **params: Any) -> httpx.Response:
        return await self.client.get("/api/v1/audit", params=params)


@pytest.fixture
async def env(tmp_path: Any) -> AsyncIterator[_Env]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repo = SqlAlchemyAuditRepo(session_maker(engine))
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(audit_router)
    app.dependency_overrides[get_audit_service] = lambda: AuditService(repo)
    app.dependency_overrides[get_resource_service] = lambda: None
    set_active_token(_TOKEN)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost", headers={"X-Coffer-Token": _TOKEN}
    ) as client:
        yield _Env(client, repo)
    await engine.dispose()


def _events(body: dict[str, Any]) -> list[str]:
    return [e["event_type"] for e in body["entries"]]


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="a page read after new rows arrive neither repeats nor skips",
)
async def test_a_page_after_new_rows_neither_repeats_nor_skips(env: _Env) -> None:
    # e2 and e3 share a timestamp: the id breaks the tie, newest id first.
    for event, minutes in (("e1", 0), ("e2", 1), ("e3", 1), ("e4", 2), ("e5", 3)):
        await env.record(event, _T0 + timedelta(minutes=minutes))

    first = (await env.read(limit=2)).json()
    assert _events(first) == ["e5", "e4"]
    await env.record("new", _T0 + timedelta(minutes=10))
    second = (await env.read(limit=2, cursor=first["next_cursor"])).json()
    third = (await env.read(limit=2, cursor=second["next_cursor"])).json()

    seen = _events(first) + _events(second) + _events(third)
    assert seen == ["e5", "e4", "e3", "e2", "e1"]
    assert third["next_cursor"] is None


@pytest.mark.acceptance(spec="resource-framework", scenario="the last page carries no next cursor")
async def test_the_last_page_carries_no_next_cursor(env: _Env) -> None:
    for event, minutes in (("e1", 0), ("e2", 1), ("e3", 2)):
        await env.record(event, _T0 + timedelta(minutes=minutes))

    body = (await env.read(limit=3)).json()

    assert _events(body) == ["e3", "e2", "e1"]
    assert body["next_cursor"] is None


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a malformed or foreign cursor is refused"
)
async def test_a_malformed_or_foreign_cursor_is_refused(env: _Env) -> None:
    for event, minutes in (("e1", 0), ("e2", 1), ("e3", 2)):
        await env.record(event, _T0 + timedelta(minutes=minutes))
    issued = (await env.read(kind="fake_kind", limit=1)).json()["next_cursor"]
    assert issued is not None

    foreign = await env.read(kind="other_kind", limit=1, cursor=issued)
    malformed = await env.read(kind="fake_kind", limit=1, cursor="not-a-cursor!")

    for r in (foreign, malformed):
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "CURSOR_INVALID"
    # The cursor still reads the list it was issued for.
    assert (await env.read(kind="fake_kind", limit=1, cursor=issued)).status_code == 200


# revise-web-ui-ia: resource-framework "a page carries the count of every matching row" —
# the acceptance marker is added when the change is archived.
async def test_a_page_carries_the_count_of_every_matching_row(env: _Env) -> None:
    for event, minutes, kind in (
        ("e1", 0, "fake_kind"),
        ("e2", 1, "other_kind"),
        ("e3", 2, "fake_kind"),
        ("e4", 3, "other_kind"),
        ("e5", 4, "fake_kind"),
    ):
        await env.record(event, _T0 + timedelta(minutes=minutes), kind=kind)

    first = (await env.read(kind="fake_kind", limit=2)).json()
    second = (await env.read(kind="fake_kind", limit=2, cursor=first["next_cursor"])).json()

    assert _events(first) == ["e5", "e3"]
    assert _events(second) == ["e1"]
    assert first["total"] == 3
    assert second["total"] == 3


async def test_total_follows_every_filter(env: _Env) -> None:
    for event, minutes in (
        ("memory.a", 0),
        ("memory.b", 1),
        ("skill.a", 2),
        ("memory.a", 3),
    ):
        await env.record(event, _T0 + timedelta(minutes=minutes))

    assert (await env.read()).json()["total"] == 4
    assert (await env.read(event_prefix="memory.")).json()["total"] == 3
    assert (await env.read(event_type="memory.a")).json()["total"] == 2
    since = (_T0 + timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    assert (await env.read(since=since)).json()["total"] == 2
    assert (await env.read(kind="nothing_here")).json() == {
        "entries": [],
        "next_cursor": None,
        "total": 0,
    }
