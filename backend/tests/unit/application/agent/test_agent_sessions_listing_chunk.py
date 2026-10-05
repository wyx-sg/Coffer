"""``AgentSessionsListing`` asks each agent for a fixed chunk, not the page size."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from coffer.application.agent.agent_sessions_listing import AGENT_PAGE, AgentSessionsListing
from coffer.domain.agent.native_sessions import NativeSession, NativeSessionPage
from coffer.domain.resource import Resource

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


class _Agents:
    async def list(self) -> list[Resource]:
        return [
            Resource(
                uid="a1",
                kind="agent",
                name="codex",
                description=None,
                config={"type": "codex"},
                enabled=True,
                created_at=_NOW,
                updated_at=_NOW,
            )
        ]


class _Sessions:
    def __init__(self) -> None:
        self.limits: list[int] = []

    async def list(self, uid: str, **kw: Any) -> NativeSessionPage:
        self.limits.append(kw["limit"])
        items = [
            NativeSession(
                session_id=f"s{i}",
                title="t",
                cwd=None,
                created_at=_NOW,
                last_activity_at=_NOW.replace(minute=59 - i % 50),
            )
            for i in range(AGENT_PAGE)
        ]
        return NativeSessionPage(items=items, next_cursor=None, total=None, conversations={})


async def test_page_is_cut_to_limit_but_agent_is_asked_for_the_fixed_chunk() -> None:
    sessions = _Sessions()
    listing = AgentSessionsListing(agents=_Agents(), sessions=sessions)  # type: ignore[arg-type]
    page = await listing.list(limit=30)
    assert len(page.items) == 30
    assert sessions.limits == [AGENT_PAGE]
    assert page.next_cursor is not None
