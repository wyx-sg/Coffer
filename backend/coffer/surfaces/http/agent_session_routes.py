"""/api/v1/agents/{uid}/sessions* — the agent's own conversations.

The agent keeps its sessions (Claude Code in its project files, Codex in its
thread store) and answers for them: the listing is the agent's own, read through
the Claude Agent SDK or a short-lived ``codex app-server``. Coffer keeps no copy
and no message text; a row is ``session_id``, ``title``, ``cwd`` and two times.

``GET`` searches (case-insensitively; Claude Code over title and working
directory, Codex over the title — its server's own filter) and pages by an
opaque ``cursor``. ``total`` is the number of matches, or ``null`` where the
agent cannot count them without reading everything (Codex). ``PATCH`` renames
and ``DELETE`` deletes the session in the agent's own store.

Nothing here is audited (spec agent-registry "Audit every agent lifecycle
event"): the listing is read-only, and rename and delete are the agent's own act
on its own record. A session that a channel conversation points at also carries
that conversation (``conversation_id``, ``running``, ``needs_you``,
``channel_binding``); renaming it retitles the conversation and deleting it
cancels the conversation's turn and removes its index row.

A session id that is not ``[A-Za-z0-9-]{1,128}``, or one the agent rejects as
malformed, is 400; an unknown session is 404; an agent type with no listing is
400.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field

from coffer.application.agent.agent_sessions_listing import AgentSessionsListing, ListedSession
from coffer.application.agent.native_session_service import NativeSessionService
from coffer.domain.agent.native_sessions import (
    NativeSession,
    SessionChannel,
    SessionConversation,
)
from coffer.domain.channel_type import ChannelType
from coffer.surfaces.http.agent_type_path import resolve_agent_path
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.workspace_dependencies import (
    get_agent_sessions_listing,
    get_native_session_service,
)

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token), Depends(resolve_agent_path)],
)


all_router = APIRouter(
    prefix="/api/v1/agent-sessions",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


class SessionPlaceOut(BaseModel):
    """Which chat and thread of its channel a conversation lives in."""

    chat_kind: Literal["direct", "group"] | None = None
    thread: bool = False
    parallel_mark: str | None = None
    chat_name: str | None = None


class SessionChannelOut(BaseModel):
    """The IM channel a session's conversation is driven from."""

    channel_uid: str
    #: The channel's label now; null when the channel was deleted.
    channel: str | None
    chat_id: str
    #: The channel's type key; null when the channel was deleted.
    platform: ChannelType | None = None
    place: SessionPlaceOut | None = None


class AgentSessionOut(BaseModel):
    """One of the agent's sessions as the list shows it."""

    session_id: str
    #: The agent's own title (custom title, summary or first prompt), scrubbed
    #: of well-known secret shapes.
    title: str
    cwd: str | None = None
    created_at: datetime | None = None
    last_activity_at: datetime | None = None
    #: The channel conversation that points at this session; null when none does.
    conversation_id: str | None = None
    #: A turn is in flight on the session's conversation right now.
    running: bool = False
    #: A question the agent asked on the session's conversation waits for the owner.
    needs_you: bool = False
    #: The conversation's channel binding; null when no conversation points here.
    channel_binding: SessionChannelOut | None = None


class AgentSessionListResponse(BaseModel):
    """Response for GET /api/v1/agents/{uid}/sessions."""

    sessions: list[AgentSessionOut]
    #: Reads the page after this one; null on the last page.
    next_cursor: str | None
    #: Sessions matching ``q``; null where the agent cannot count them cheaply.
    total: int | None


class AgentSessionRowOut(AgentSessionOut):
    """A row of the cross-agent list: the agent's session row plus whose it is."""

    #: The agent's key (its type, e.g. ``claude_code``).
    agent_key: str
    #: Null for a channel conversation on which no turn has run yet.
    session_id: str | None = None  # type: ignore[assignment]


class UnavailableAgentOut(BaseModel):
    """An agent whose sessions could not be read."""

    agent: str
    reason: str


class AllAgentSessionsResponse(BaseModel):
    """Response for GET /api/v1/agent-sessions (no ``total``: an agent may not count)."""

    sessions: list[AgentSessionRowOut]
    #: Reads the page after this one; null on the last page.
    next_cursor: str | None
    #: Agents left out of this page because their listing failed.
    unavailable: list[UnavailableAgentOut]


class AgentSessionRename(BaseModel):
    """Body of PATCH /api/v1/agents/{uid}/sessions/{session_id}."""

    title: str = Field(min_length=1, max_length=500)


def _binding(channel: SessionChannel | None) -> SessionChannelOut | None:
    if channel is None:
        return None
    place = channel.place
    return SessionChannelOut(
        channel_uid=channel.channel_uid,
        channel=channel.channel,
        chat_id=channel.chat_id,
        platform=channel.platform,  # type: ignore[arg-type]
        place=(
            SessionPlaceOut(
                chat_kind=place.chat_kind,  # type: ignore[arg-type]
                thread=place.thread,
                parallel_mark=place.parallel_mark,
                chat_name=place.chat_name,
            )
            if place is not None
            else None
        ),
    )


def _row(s: NativeSession, conv: SessionConversation | None) -> AgentSessionOut:
    return AgentSessionOut(
        session_id=s.session_id,
        title=s.title,
        cwd=s.cwd,
        created_at=s.created_at,
        last_activity_at=s.last_activity_at,
        conversation_id=conv.conversation_id if conv is not None else None,
        running=conv.running if conv is not None else False,
        needs_you=conv.needs_you if conv is not None else False,
        channel_binding=_binding(conv.channel) if conv is not None else None,
    )


def _listed_row(row: ListedSession) -> AgentSessionRowOut:
    conv = row.conversation
    return AgentSessionRowOut(
        agent_key=row.agent_key,
        session_id=row.session_id,
        title=row.title,
        cwd=row.cwd,
        created_at=row.created_at,
        last_activity_at=row.last_activity_at,
        conversation_id=conv.conversation_id if conv is not None else None,
        running=conv.running if conv is not None else False,
        needs_you=conv.needs_you if conv is not None else False,
        channel_binding=_binding(conv.channel) if conv is not None else None,
    )


@all_router.get("", response_model=AllAgentSessionsResponse)
async def list_all_agent_sessions(
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(
        None,
        description=(
            "The previous page's next_cursor. Bound to the filters it was issued "
            "for; any other value is 400 CURSOR_INVALID."
        ),
    ),
    q: str | None = Query(
        None,
        max_length=200,
        description="Title or working directory contains this text (each agent's own search).",
    ),
    source: str | None = Query(
        None,
        max_length=2000,
        description=(
            "Comma-separated `local` (sessions no channel conversation points at) and "
            "channel uids. Absent is everything."
        ),
    ),
    agent: str | None = Query(
        None,
        max_length=2000,
        description="Comma-separated agent keys (e.g. `claude_code,codex`). Absent is every agent.",
    ),
    svc: AgentSessionsListing = Depends(get_agent_sessions_listing),  # noqa: B008
) -> AllAgentSessionsResponse:
    """Every managed agent's sessions, newest activity first (agent key and
    session id break ties), paged by one opaque cursor."""
    page = await svc.list(limit=limit, cursor=cursor, q=q, source=source, agent=agent)
    return AllAgentSessionsResponse(
        sessions=[_listed_row(r) for r in page.items],
        next_cursor=page.next_cursor,
        unavailable=[UnavailableAgentOut(agent=u.agent, reason=u.reason) for u in page.unavailable],
    )


@router.get("/{uid}/sessions", response_model=AgentSessionListResponse)
async def list_agent_sessions(
    uid: str,
    q: str | None = Query(None, description="Case-insensitive search (Codex: title only)."),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(
        None,
        description=(
            "The previous page's next_cursor. Bound to the agent and search it was "
            "issued with; any other value is 400 CURSOR_INVALID."
        ),
    ),
    svc: NativeSessionService = Depends(get_native_session_service),  # noqa: B008
) -> AgentSessionListResponse:
    """The agent's sessions, most recent activity first."""
    page = await svc.list(uid, q=q, limit=limit, cursor=cursor)
    return AgentSessionListResponse(
        sessions=[_row(s, page.conversations.get(s.session_id)) for s in page.items],
        next_cursor=page.next_cursor,
        total=page.total,
    )


@router.patch(
    "/{uid}/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def rename_agent_session(
    uid: str,
    session_id: str,
    body: AgentSessionRename,
    svc: NativeSessionService = Depends(get_native_session_service),  # noqa: B008
) -> None:
    """Rename the session in the agent's own store."""
    await svc.rename(uid, session_id, body.title)


@router.delete(
    "/{uid}/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_agent_session(
    uid: str,
    session_id: str,
    svc: NativeSessionService = Depends(get_native_session_service),  # noqa: B008
) -> None:
    """Delete the session from the agent's own store (permanent)."""
    await svc.delete(uid, session_id)
