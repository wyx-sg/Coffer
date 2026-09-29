"""AgentTranscriptService — read a registered agent's local transcript sessions.

A thin read-only query service: resolve the agent to its type + config dir, then hand
the search/sort/page — or the single-session read behind one conversation's page — to
the reader adapter. It writes nothing and reads nothing but the agent's own ``.jsonl``
files, and (like every other workspace listing, spec agent-registry "Audit every agent
lifecycle event") it records no audit event for either.
"""

from __future__ import annotations

import asyncio
import functools
from datetime import datetime
from typing import Any, Protocol

from coffer.application.agent.service import AgentService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.transcripts import (
    TranscriptSession,
    TranscriptSessionBody,
    session_sort_key,
)
from coffer.domain.pagination import CursorInvalid, Page, decode_cursor, paginate, position_of


class TranscriptReaderPort(Protocol):
    """Read-only transcript discovery; implemented in ``infrastructure/agent``."""

    def search_session_summaries(
        self,
        *,
        agent_type_value: str,
        config_dir: str,
        limit: int,
        after: tuple[Any, str] | None = ...,
        query: str | None = ...,
        project: str | None = ...,
        sort: str = ...,
        order: str = ...,
    ) -> tuple[int, list[TranscriptSession]]: ...

    def read_session(
        self,
        *,
        agent_type_value: str,
        config_dir: str,
        source_path: str,
        limit: int,
        offset: int,
    ) -> TranscriptSessionBody: ...


class AgentTranscriptService:
    """Lists the transcript sessions an agent has left on this machine."""

    def __init__(self, *, reader: TranscriptReaderPort, agent_service: AgentService) -> None:
        self._reader = reader
        self._agents = agent_service

    async def list_sessions(
        self,
        agent_uid: str,
        *,
        limit: int = 100,
        cursor: str | None = None,
        query: str | None = None,
        project: str | None = None,
        sort: str = "last_activity_at",
        order: str = "desc",
    ) -> tuple[int, Page[TranscriptSession]]:
        """Return ``(matched_total, page)`` for the agent with *agent_uid*.

        The page is keyed on ``(sort value, session_id)`` and continued by
        ``cursor`` (spec resource-framework "Page growing lists by an opaque
        cursor"): an agent writes new sessions while a reader pages, and an
        offset would shift under them. The cursor is bound to the agent, the
        search, the filter and the sort; any other is ``CursorInvalid``.

        Raises ``ResourceNotFound`` when no such agent is registered, and
        ``UnsupportedAgentTypeError`` when its type has no transcript layout.
        Backed by the reader's mtime-aware cache, so an agent with thousands of
        past sessions stays responsive.
        """
        filters = {
            "agent": agent_uid,
            "q": query,
            "project": project,
            "sort": sort,
            "order": order,
        }
        resource = await self._agents.get(agent_uid)
        cfg = AgentConfig.model_validate(resource.config)
        after = _after(decode_cursor(cursor, list_tag="transcripts", filters=filters), sort)
        # A cold cache parses every .jsonl the agent ever wrote — thousands of
        # files, seconds of blocking I/O. The daemon serves the MCP gateway from
        # this same loop, so the read runs off it. (Concurrent calls may parse
        # the same file twice; the reader's cache tolerates that, and the second
        # writer simply stores the same entry.)
        total, rows = await asyncio.to_thread(
            functools.partial(
                self._reader.search_session_summaries,
                agent_type_value=cfg.type.value,
                config_dir=str(cfg.resolved_config_dir()),
                limit=limit + 1,
                after=after,
                query=query,
                project=project,
                sort=sort,
                order=order,
            )
        )
        page = paginate(
            rows,
            limit,
            list_tag="transcripts",
            filters=filters,
            key=lambda s: position_of(session_sort_key(s, sort), s.session_id),
        )
        return total, page

    async def read_session(
        self,
        agent_uid: str,
        *,
        source_path: str,
        limit: int = 200,
        offset: int = 0,
    ) -> TranscriptSessionBody:
        """One session of that agent: its summary plus a window of its turns.

        ``source_path`` is a path the listing handed out. The reader is the one
        that decides whether it really is one of this agent's transcripts — the
        check belongs beside the sessions-directory layout, not here — so this
        method's whole job is the agent lookup and keeping the disk read off the
        event loop.

        Raises ``ResourceNotFound`` when no such agent is registered,
        ``UnsupportedAgentTypeError`` when its type has no transcript layout,
        ``ValueError`` when the path is not one of this agent's transcripts, and
        ``FileNotFoundError`` when the file is gone.
        """
        resource = await self._agents.get(agent_uid)
        cfg = AgentConfig.model_validate(resource.config)
        # A cold summary is a full parse of one file, which for a long session
        # is tens of megabytes of blocking I/O; the daemon serves the MCP
        # gateway from this same loop, so the read runs off it.
        return await asyncio.to_thread(
            functools.partial(
                self._reader.read_session,
                agent_type_value=cfg.type.value,
                config_dir=str(cfg.resolved_config_dir()),
                source_path=source_path,
                limit=limit,
                offset=offset,
            )
        )


def _after(position: list[Any] | None, sort: str) -> tuple[Any, str] | None:
    """A decoded ``[sort value, session_id]`` position back in its typed form."""
    if position is None:
        return None
    if len(position) != 2 or not isinstance(position[1], str):
        raise CursorInvalid("its position does not fit this list")
    value, session_id = position
    if sort == "message_count":
        if not isinstance(value, int) or isinstance(value, bool):
            raise CursorInvalid("its position does not fit this list")
        return value, session_id
    try:
        return datetime.fromisoformat(value), session_id
    except (TypeError, ValueError) as exc:
        raise CursorInvalid("its position does not fit this list") from exc
