"""NativeSessionService — list, rename and delete an agent's own sessions.

The agents keep their conversations themselves, so this service holds none: it
resolves the registered agent to its type and config dir, hands the work to the
per-type :class:`NativeSessionSource` (infrastructure — the Claude Agent SDK, a
short-lived ``codex app-server``), and shapes the answer into one page type.

Nothing here is audited: listing is a read-only workspace listing, and rename
and delete are the agent's own act on its own record (spec agent-registry
"Audit every agent lifecycle event", "Rename and delete a native session
through the agent").

Paging reuses the repo's cursor (``domain/pagination``). A source pages by a
*position* of its own — the last row's activity time and session id for Claude
Code, the server's ``nextCursor`` for Codex — and this service wraps it in a
cursor bound to the agent and the search, so a cursor issued for one search
cannot be replayed with another.

A session that a channel conversation points at is joined to it through the
:class:`SessionConversations` port, which the composition root satisfies with
the turn platform (this kind never imports it).
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.native_sessions import (
    NativeSession,
    NativeSessionInvalid,
    NativeSessionPage,
    SessionConversation,
    UnsupportedAgentType,
    is_session_id,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.pagination import decode_cursor, encode_cursor
from coffer.domain.resource import Resource

_LIST_TAG = "native-sessions"


@dataclass(frozen=True)
class SourcePage:
    """What a source answers for one list call.

    ``next_position`` is the keyset position the next page continues after
    (``None`` on the last page); ``total`` is the number of matching sessions,
    or ``None`` where the source cannot count without reading everything.
    """

    items: list[NativeSession]
    next_position: list[Any] | None
    total: int | None


class NativeSessionSource(Protocol):
    """One agent type's sessions, read and changed through the agent itself.

    Implemented in ``infrastructure/agent`` (``claude_native_sessions``,
    ``codex_native_sessions``). ``rename`` and ``delete`` raise
    ``NativeSessionNotFound`` / ``NativeSessionInvalid``.
    """

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage: ...

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None: ...

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None: ...


class SessionConversations(Protocol):
    """The turn platform's conversations, as the sessions tab needs them.

    Declared here by the kind that consumes it; the composition root satisfies
    it so this kind never imports the chat kind.
    """

    async def linked(self, session_ids: Sequence[str]) -> Mapping[str, SessionConversation]:
        """The conversation each of ``session_ids`` belongs to; the others are
        absent. A constant number of reads whatever the number of ids."""
        ...

    async def retitle(self, session_id: str, title: str) -> None:
        """Give the conversation pointing at the session that title (no-op when
        none does)."""
        ...

    async def forget(self, session_id: str) -> None:
        """Cancel any turn in flight on the session and remove the conversation's
        index row (no-op when no conversation points at it)."""
        ...


class _AgentLookup(Protocol):
    async def get(self, uid: str) -> Resource: ...


class NativeSessionService:
    """An agent's native sessions, through the source for its type."""

    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        sources: Mapping[AgentType, NativeSessionSource],
        conversations: SessionConversations | None = None,
    ) -> None:
        self._agents = agent_service
        self._sources = sources
        self._conversations = conversations

    def link_conversations(self, conversations: SessionConversations | None) -> None:
        """Called by the composition root once the turn platform is wired."""
        self._conversations = conversations

    async def list(
        self,
        agent_uid: str,
        *,
        q: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> NativeSessionPage:
        """One page of the agent's sessions, newest activity first.

        Raises ``ResourceNotFound`` for an unknown agent, ``UnsupportedAgentType``
        when its type has no source and ``CursorInvalid`` for a cursor issued for
        another agent or search.
        """
        _agent, cfg, source = await self._resolve(agent_uid)
        query = (q or "").strip() or None
        filters = {"agent": agent_uid, "q": query}
        position = decode_cursor(cursor, list_tag=_LIST_TAG, filters=filters)
        page = await source.list(cfg.resolved_config_dir(), q=query, limit=limit, position=position)
        next_cursor = (
            encode_cursor(_LIST_TAG, filters, page.next_position)
            if page.next_position is not None
            else None
        )
        linked = (
            await self._conversations.linked([s.session_id for s in page.items])
            if self._conversations is not None and page.items
            else {}
        )
        return NativeSessionPage(
            items=page.items, next_cursor=next_cursor, total=page.total, conversations=linked
        )

    async def rename(self, agent_uid: str, session_id: str, title: str) -> None:
        """Give the session a new title, in the agent's own store; a conversation
        pointing at it takes the title too."""
        _require_id(session_id)
        clean = title.strip()
        if not clean:
            raise NativeSessionInvalid("title must not be empty")
        _agent, cfg, source = await self._resolve(agent_uid)
        await source.rename(cfg.resolved_config_dir(), session_id, clean)
        if self._conversations is not None:
            await self._conversations.retitle(session_id, clean)

    async def delete(self, agent_uid: str, session_id: str) -> None:
        """Delete the session from the agent's own store (permanent); a
        conversation pointing at it loses its turn and its index row. Nothing of
        Coffer's changes when the agent refuses."""
        _require_id(session_id)
        _agent, cfg, source = await self._resolve(agent_uid)
        await source.delete(cfg.resolved_config_dir(), session_id)
        if self._conversations is not None:
            await self._conversations.forget(session_id)

    async def _resolve(self, agent_uid: str) -> tuple[Resource, AgentConfig, NativeSessionSource]:
        agent = await self._agents.get(agent_uid)
        cfg = AgentConfig.model_validate(agent.config)
        source = self._sources.get(cfg.type)
        if source is None:
            raise UnsupportedAgentType(cfg.type.value)
        return agent, cfg, source


def _require_id(session_id: str) -> None:
    if not is_session_id(session_id):
        raise NativeSessionInvalid(f"not a session id: {session_id!r}")


__all__ = ["NativeSessionService", "NativeSessionSource", "SessionConversations", "SourcePage"]
