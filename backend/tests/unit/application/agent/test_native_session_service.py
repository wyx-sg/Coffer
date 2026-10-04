"""``NativeSessionService``: per-type dispatch, cursor binding, conversations.

Fake sources stand in for the Agent SDK and the Codex app-server; the agent
lookup is a dict. Covers the paging contract (a source's position travels inside
an opaque cursor bound to the agent and the search), the join with the turn
platform's conversations (rows carry them; rename retitles, delete forgets, a
refusal changes nothing there) and the error cases.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.agent.native_session_service import NativeSessionService, SourcePage
from coffer.domain.agent.native_sessions import (
    NativeSession,
    NativeSessionInvalid,
    NativeSessionNotFound,
    SessionChannel,
    SessionConversation,
    UnsupportedAgentType,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.pagination import CursorInvalid
from coffer.domain.resource import Resource

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _agent(uid: str, agent_type: str, config_dir: str) -> Resource:
    return Resource(
        uid=uid,
        kind="agent",
        name=agent_type.replace("_", "-"),
        description=None,
        config={"type": agent_type, "config_dir": config_dir},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


class _Agents:
    def __init__(self, *agents: Resource) -> None:
        self._by_uid = {a.uid: a for a in agents}

    async def get(self, uid: str) -> Resource:
        try:
            return self._by_uid[uid]
        except KeyError:
            raise ResourceNotFound(uid) from None


class _Source:
    """Pages over ``rows``; the position is ``[offset]``."""

    def __init__(self, rows: list[NativeSession], *, total: int | None) -> None:
        self.rows = rows
        self.total = total
        self.list_calls: list[tuple[pathlib.Path, str | None, int, list[Any] | None]] = []
        self.changes: list[tuple[str, str, str | None]] = []
        self.refuse: Exception | None = None

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        self.list_calls.append((config_dir, q, limit, position))
        start = int(position[0]) if position else 0
        rows = [r for r in self.rows if not q or q in r.title]
        window = rows[start : start + limit]
        more = start + limit < len(rows)
        return SourcePage(window, [start + limit] if more else None, self.total)

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None:
        if self.refuse is not None:
            raise self.refuse
        self.changes.append(("rename", session_id, title))

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None:
        if self.refuse is not None:
            raise self.refuse
        self.changes.append(("delete", session_id, None))


class _Conversations:
    """The turn platform's side: one channel conversation on session ``s1``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self.link = SessionConversation(
            "conv-1",
            running=True,
            needs_you=False,
            channel=SessionChannel("chan-1", "SeaTalk", "chat-9", "seatalk"),
        )

    async def linked(self, session_ids: Sequence[str]) -> Mapping[str, SessionConversation]:
        return {"s1": self.link} if "s1" in session_ids else {}

    async def retitle(self, session_id: str, title: str) -> None:
        self.calls.append(("retitle", session_id, title))

    async def forget(self, session_id: str) -> None:
        self.calls.append(("forget", session_id, None))


def _rows(n: int) -> list[NativeSession]:
    return [NativeSession(f"s{i}", f"task {i}", "/work", _NOW, _NOW) for i in range(n)]


@pytest.fixture
def parts() -> tuple[NativeSessionService, _Source, _Source, _Conversations]:
    claude = _Source(_rows(5), total=5)
    codex = _Source(_rows(3), total=None)
    conversations = _Conversations()
    service = NativeSessionService(
        agent_service=_Agents(
            _agent("u-claude", "claude_code", "/home/.claude"),
            _agent("u-codex", "codex", "/home/.codex"),
        ),
        sources={AgentType.CLAUDE_CODE: claude, AgentType.CODEX: codex},
        conversations=conversations,
    )
    return service, claude, codex, conversations


@pytest.mark.acceptance(
    spec="agent-registry", scenario="browse an agent's native sessions with title and search"
)
async def test_pages_chain_through_the_cursor_and_the_last_has_none(
    parts: tuple[NativeSessionService, _Source, _Source, _Conversations],
) -> None:
    service, claude, _codex, _conversations = parts

    first = await service.list("u-claude", limit=2)
    second = await service.list("u-claude", limit=2, cursor=first.next_cursor)
    third = await service.list("u-claude", limit=2, cursor=second.next_cursor)

    assert [s.session_id for s in first.items + second.items + third.items] == [
        "s0",
        "s1",
        "s2",
        "s3",
        "s4",
    ]
    assert first.total == 5 and third.next_cursor is None
    assert [c[3] for c in claude.list_calls] == [None, [2], [4]]
    assert claude.list_calls[0][0] == pathlib.Path("/home/.claude")


async def test_a_source_that_cannot_count_leaves_total_null(
    parts: tuple[NativeSessionService, _Source, _Source, _Conversations],
) -> None:
    service, _claude, codex, _conversations = parts

    page = await service.list("u-codex", limit=2)

    assert page.total is None and page.next_cursor is not None
    assert codex.list_calls[0][0] == pathlib.Path("/home/.codex")


async def test_search_is_passed_through_trimmed_and_blank_means_none(
    parts: tuple[NativeSessionService, _Source, _Source, _Conversations],
) -> None:
    service, claude, _codex, _conversations = parts

    found = await service.list("u-claude", q="  task 3 ", limit=5)
    await service.list("u-claude", q="   ", limit=5)

    assert [s.session_id for s in found.items] == ["s3"]
    assert [c[1] for c in claude.list_calls] == ["task 3", None]


async def test_a_cursor_is_bound_to_its_search_and_its_agent(
    parts: tuple[NativeSessionService, _Source, _Source, _Conversations],
) -> None:
    service, _claude, _codex, _conversations = parts
    first = await service.list("u-claude", q="task", limit=2)

    with pytest.raises(CursorInvalid):
        await service.list("u-claude", q="other", limit=2, cursor=first.next_cursor)
    with pytest.raises(CursorInvalid):
        await service.list("u-codex", q="task", limit=2, cursor=first.next_cursor)
    with pytest.raises(CursorInvalid):
        await service.list("u-claude", limit=2, cursor="garbage")


async def test_unknown_agent_and_unsupported_type(
    parts: tuple[NativeSessionService, _Source, _Source, _Conversations],
) -> None:
    service, *_ = parts

    with pytest.raises(ResourceNotFound):
        await service.list("nope")
    # A type with no registered source (only Claude Code's is wired here).
    claude_only = NativeSessionService(
        agent_service=_Agents(_agent("u-codex", "codex", "/home/.codex")),
        sources={AgentType.CLAUDE_CODE: _Source([], total=0)},
    )
    with pytest.raises(UnsupportedAgentType):
        await claude_only.list("u-codex")


@pytest.mark.acceptance(spec="agent-registry", scenario="rename a native session")
async def test_rename_goes_to_the_source_and_retitles_the_conversation(
    parts: tuple[NativeSessionService, _Source, _Source, _Conversations],
) -> None:
    service, claude, _codex, conversations = parts

    await service.rename("u-claude", "s1", "  Better title ")

    assert claude.changes == [("rename", "s1", "Better title")]
    assert conversations.calls == [("retitle", "s1", "Better title")]


@pytest.mark.acceptance(spec="agent-registry", scenario="delete a native session permanently")
async def test_delete_goes_to_the_source_and_forgets_the_conversation(
    parts: tuple[NativeSessionService, _Source, _Source, _Conversations],
) -> None:
    service, claude, _codex, conversations = parts

    await service.delete("u-claude", "s1")

    assert claude.changes == [("delete", "s1", None)]
    assert conversations.calls == [("forget", "s1", None)]


@pytest.mark.acceptance(spec="agent-registry", scenario="an unknown session is not found")
async def test_an_unknown_session_changes_nothing(
    parts: tuple[NativeSessionService, _Source, _Source, _Conversations],
) -> None:
    service, claude, _codex, conversations = parts
    claude.refuse = NativeSessionNotFound("nope")

    with pytest.raises(NativeSessionNotFound):
        await service.delete("u-claude", "nope")
    with pytest.raises(NativeSessionNotFound):
        await service.rename("u-claude", "nope", "Title")

    assert claude.changes == [] and conversations.calls == []


@pytest.mark.acceptance(
    spec="agent-registry", scenario="a refused operation changes nothing in Coffer"
)
async def test_a_refusal_leaves_the_conversation_alone(
    parts: tuple[NativeSessionService, _Source, _Source, _Conversations],
) -> None:
    service, claude, _codex, conversations = parts
    claude.refuse = NativeSessionInvalid("the agent says no")

    with pytest.raises(NativeSessionInvalid, match="the agent says no"):
        await service.delete("u-claude", "s1")
    with pytest.raises(NativeSessionInvalid, match="the agent says no"):
        await service.rename("u-claude", "s1", "Title")

    assert conversations.calls == []


@pytest.mark.acceptance(
    spec="agent-registry", scenario="a channel conversation's session carries its conversation"
)
async def test_a_listed_session_carries_the_conversation_pointing_at_it(
    parts: tuple[NativeSessionService, _Source, _Source, _Conversations],
) -> None:
    service, _claude, _codex, conversations = parts

    page = await service.list("u-claude", limit=5)

    assert page.conversations == {"s1": conversations.link}
    assert "s0" not in page.conversations


async def test_a_bad_id_or_title_reaches_no_source(
    parts: tuple[NativeSessionService, _Source, _Source, _Conversations],
) -> None:
    service, claude, _codex, conversations = parts

    for bad in ("../etc", "a b", "", "x" * 129, "id;rm"):
        with pytest.raises(NativeSessionInvalid):
            await service.delete("u-claude", bad)
    with pytest.raises(NativeSessionInvalid):
        await service.rename("u-claude", "abc", "   ")

    assert claude.changes == [] and conversations.calls == []
