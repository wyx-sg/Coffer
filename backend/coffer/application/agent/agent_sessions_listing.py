"""AgentSessionsListing — every managed agent's sessions in one list.

Spec agent-registry "List every agent's sessions in one list". Each agent is
asked through :class:`NativeSessionService` (concurrently) and the answers are
merged by ``(last_activity_at desc, agent key, session_id)``.

**Cursor.** An agent's own cursor only points after a page it returned, so the
merged cursor records, per agent, the agent cursor of the page its next
unconsumed row sits on and how many rows of that page are already consumed:
``{agent: {"c": <agent cursor | null>, "skip": n, "done": bool}}``. It is bound,
through ``domain/pagination``, to the ``q`` / ``source`` / ``agent`` filters it
was issued for.

**Source.** ``source`` is a set of ``local`` and channel uids. Channel uids only
are answered from the conversation index (the :class:`ChannelConversationIndex`
port — a conversation with no session yet is listed too); otherwise the merge is
post-filtered on each row's conversation binding, reading at most
:data:`MAX_PAGES_PER_AGENT` agent pages (of :data:`AGENT_PAGE` rows) per agent per
request.

**Failure.** An agent whose listing raises is left out and named in
``unavailable``; its cursor position is kept so a later read picks it up again.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from coffer.application.agent.native_session_service import NativeSessionService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.native_sessions import SessionConversation, UnsupportedAgentType
from coffer.domain.pagination import CursorInvalid, Page, decode_cursor, encode_cursor
from coffer.domain.resource import Resource

_LIST_TAG = "agent_sessions"
#: Agent pages read per agent in one request while a source filter thins the merge.
MAX_PAGES_PER_AGENT = 5
#: Rows asked of an agent per call, whatever the page size of the merged list, so
#: the first page and every later one hit the same snapshot of that agent.
AGENT_PAGE = 50
LOCAL = "local"

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ListedSession:
    """One row of the cross-agent list. ``session_id`` is ``None`` for a channel
    conversation on which no turn has run."""

    agent_key: str
    session_id: str | None
    title: str
    cwd: str | None
    created_at: datetime | None
    last_activity_at: datetime | None
    conversation: SessionConversation | None = None


@dataclass(frozen=True)
class UnavailableAgent:
    """An agent whose sessions could not be read, and why."""

    agent: str
    reason: str


@dataclass(frozen=True)
class AgentSessionsPage(Page[ListedSession]):
    """A page of the merged list; ``unavailable`` names the agents left out."""

    unavailable: list[UnavailableAgent] = field(default_factory=list)


class ChannelConversationIndex(Protocol):
    """The channel conversations of the conversation index as list rows.

    Declared here by the kind that consumes it; the composition root satisfies
    it with the chat kind's service so this kind never imports it.
    """

    async def page(
        self,
        *,
        limit: int,
        cursor: str | None,
        q: str | None,
        channels: Sequence[str],
        agents: Sequence[str],
    ) -> Page[ListedSession]: ...


class _AgentLister(Protocol):
    async def list(self) -> list[Resource]: ...


def _tokens(csv: str | None) -> list[str]:
    return sorted({t for t in (p.strip() for p in (csv or "").split(",")) if t})


@dataclass
class _Stream:
    """One agent's rows, read page by page from the position the cursor named."""

    uid: str
    key: str
    c: str | None = None  # cursor of the page the next unconsumed row is on
    skip: int = 0  # rows of that page consumed before this request
    done: bool = False
    items: list[ListedSession] = field(default_factory=list)
    idx: int = 0
    next: str | None = None
    loaded: bool = False
    pages: int = 0
    failed: bool = False

    def head(self) -> ListedSession | None:
        return self.items[self.idx] if self.loaded and self.idx < len(self.items) else None

    def needs_load(self) -> bool:
        return not (self.done or self.failed or self.loaded)

    def settle(self) -> None:
        """After a load or a take: step past an exhausted page."""
        while self.loaded and self.idx >= len(self.items):
            if self.next is None:
                self.done = True
                return
            self.c, self.skip, self.loaded = self.next, 0, False
            return

    def take(self) -> ListedSession:
        row = self.items[self.idx]
        self.idx += 1
        self.settle()
        return row

    def state(self) -> dict[str, Any]:
        if self.done:
            return {"done": True}
        return {"c": self.c, "skip": self.idx if self.loaded else self.skip, "done": False}


# Module-level aliases: inside the listing class, ``list`` names its method.
_Streams = list[_Stream]
_Strs = list[str]
_Rows = list[ListedSession]


def _sort_key(row: ListedSession) -> tuple[float, str, str]:
    ts = row.last_activity_at.timestamp() if row.last_activity_at is not None else float("-inf")
    return (-ts, row.agent_key, row.session_id or "")


class AgentSessionsListing:
    """The merged, filtered, paged list of every managed agent's sessions."""

    def __init__(
        self,
        *,
        agents: _AgentLister,
        sessions: NativeSessionService,
        index: ChannelConversationIndex | None = None,
    ) -> None:
        self._agents = agents
        self._sessions = sessions
        self._index = index

    def link_index(self, index: ChannelConversationIndex | None) -> None:
        """Called by the composition root once the turn platform is wired."""
        self._index = index

    async def list(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        q: str | None = None,
        source: str | None = None,
        agent: str | None = None,
    ) -> AgentSessionsPage:
        """One page, newest activity first. Raises ``CursorInvalid`` for a cursor
        issued for other filters."""
        query = (q or "").strip() or None
        sources = _tokens(source)
        agent_keys = _tokens(agent)
        channels = [s for s in sources if s != LOCAL]
        if channels and LOCAL not in sources:
            return await self._from_index(limit, cursor, query, channels, agent_keys)
        filters = {"q": query, "source": sources, "agent": agent_keys}
        saved = self._read_state(cursor, filters)
        streams = await self._streams(agent_keys, saved)
        return await self._merge(streams, filters, limit, query, set(sources))

    async def _from_index(
        self, limit: int, cursor: str | None, q: str | None, channels: _Strs, agents: _Strs
    ) -> AgentSessionsPage:
        if self._index is None:
            return AgentSessionsPage(items=[], next_cursor=None)
        page = await self._index.page(
            limit=limit, cursor=cursor, q=q, channels=channels, agents=agents
        )
        return AgentSessionsPage(items=page.items, next_cursor=page.next_cursor)

    @staticmethod
    def _read_state(cursor: str | None, filters: dict[str, Any]) -> dict[str, dict[str, Any]]:
        pos = decode_cursor(cursor, list_tag=_LIST_TAG, filters=filters)
        if pos is None:
            return {}
        state = pos[0] if len(pos) == 1 else None
        if not isinstance(state, dict) or not all(isinstance(v, dict) for v in state.values()):
            raise CursorInvalid("its position does not fit this list")
        return state

    async def _streams(self, agent_keys: _Strs, saved: dict[str, dict[str, Any]]) -> _Streams:
        streams: _Streams = []
        for resource in await self._agents.list():
            key = AgentConfig.model_validate(resource.config).type.value
            if agent_keys and key not in agent_keys:
                continue
            st = _Stream(uid=resource.uid, key=key)
            mine = saved.get(key)
            if mine is not None:
                st.done = bool(mine.get("done"))
                st.c = mine.get("c") if isinstance(mine.get("c"), str) else None
                skip = mine.get("skip")
                st.skip = skip if isinstance(skip, int) and skip >= 0 else 0
            streams.append(st)
        streams.sort(key=lambda s: s.key)
        return streams

    async def _load(self, st: _Stream, q: str | None, unavailable: dict[str, str]) -> None:
        try:
            page = await self._sessions.list(st.uid, q=q, limit=AGENT_PAGE, cursor=st.c)
        except UnsupportedAgentType:
            st.done = True
            return
        except CursorInvalid:
            raise
        except Exception as exc:
            _log.warning("agent sessions: %s listing failed: %s", st.key, exc)
            st.failed = True
            unavailable[st.key] = str(exc) or type(exc).__name__
            return
        st.items = [
            ListedSession(
                agent_key=st.key,
                session_id=s.session_id,
                title=s.title,
                cwd=s.cwd,
                created_at=s.created_at,
                last_activity_at=s.last_activity_at,
                conversation=page.conversations.get(s.session_id),
            )
            for s in page.items
        ]
        st.idx = min(st.skip, len(st.items))
        st.next = page.next_cursor
        st.loaded = True
        st.pages += 1
        st.settle()

    async def _merge(
        self,
        streams: _Streams,
        filters: dict[str, Any],
        limit: int,
        q: str | None,
        sources: set[str],
    ) -> AgentSessionsPage:
        unavailable: dict[str, str] = {}
        out: _Rows = []
        while len(out) < limit:
            loading = [s for s in streams if s.needs_load()]
            if any(s.pages >= MAX_PAGES_PER_AGENT for s in loading):
                break  # cannot see that agent's head within the budget
            await asyncio.gather(*(self._load(s, q, unavailable) for s in loading))
            heads = [(s, h) for s in streams if (h := s.head()) is not None]
            if not heads:
                if any(s.needs_load() for s in streams):
                    continue
                break
            winner, row = min(heads, key=lambda pair: _sort_key(pair[1]))
            winner.take()
            if _matches(row, sources):
                out.append(row)
        state = {s.key: s.state() for s in streams}
        more = any(not s.done for s in streams)
        next_cursor = encode_cursor(_LIST_TAG, filters, [state]) if more else None
        return AgentSessionsPage(
            items=out,
            next_cursor=next_cursor,
            unavailable=[UnavailableAgent(k, r) for k, r in sorted(unavailable.items())],
        )


def _matches(row: ListedSession, sources: set[str]) -> bool:
    if not sources:
        return True
    channel = row.conversation.channel if row.conversation is not None else None
    if channel is None:
        return LOCAL in sources
    return channel.channel_uid in sources


__all__ = [
    "AGENT_PAGE",
    "LOCAL",
    "MAX_PAGES_PER_AGENT",
    "AgentSessionsListing",
    "AgentSessionsPage",
    "ChannelConversationIndex",
    "ListedSession",
    "UnavailableAgent",
]
