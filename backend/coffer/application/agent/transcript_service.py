"""AgentTranscriptService — read a registered agent's local transcript sessions.

A thin read-only query service: resolve the agent to its type + config dir, then
hand the search/sort/page — or the single-session read behind one conversation's
page — to the reader adapter. It writes nothing and reads nothing but the
agent's own ``.jsonl`` files, and (like every other workspace listing, spec
agent-registry FR-011) it records no audit event for either.
"""

from __future__ import annotations

import asyncio
import functools
from typing import Protocol

from coffer.application.agent.service import AgentService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.transcripts import TranscriptSession, TranscriptSessionBody


class TranscriptReaderPort(Protocol):
    """Read-only transcript discovery; implemented in ``infrastructure/agent``."""

    def search_session_summaries(
        self,
        *,
        agent_type_value: str,
        config_dir: str,
        limit: int,
        offset: int,
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
        agent_name: str,
        *,
        limit: int = 100,
        offset: int = 0,
        query: str | None = None,
        project: str | None = None,
        sort: str = "last_activity_at",
        order: str = "desc",
    ) -> tuple[int, list[TranscriptSession]]:
        """Return ``(matched_total, page)`` for *agent_name*.

        Raises ``ResourceNotFound`` when no such agent is registered, and
        ``UnsupportedAgentTypeError`` when its type has no transcript layout.
        Backed by the reader's mtime-aware cache, so an agent with thousands of
        past sessions stays responsive.
        """
        resource = await self._agents.get(agent_name)
        cfg = AgentConfig.model_validate(resource.config)
        # A cold cache parses every .jsonl the agent ever wrote — thousands of
        # files, seconds of blocking I/O. The daemon serves the MCP gateway from
        # this same loop, so the read runs off it. (Concurrent calls may parse
        # the same file twice; the reader's cache tolerates that, and the second
        # writer simply stores the same entry.)
        return await asyncio.to_thread(
            functools.partial(
                self._reader.search_session_summaries,
                agent_type_value=cfg.type.value,
                config_dir=str(cfg.resolved_config_dir()),
                limit=limit,
                offset=offset,
                query=query,
                project=project,
                sort=sort,
                order=order,
            )
        )

    async def read_session(
        self,
        agent_name: str,
        *,
        source_path: str,
        limit: int = 200,
        offset: int = 0,
    ) -> TranscriptSessionBody:
        """One session of *agent_name*: its summary plus a window of its turns.

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
        resource = await self._agents.get(agent_name)
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
