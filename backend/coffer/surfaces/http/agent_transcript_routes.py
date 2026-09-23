"""GET /api/v1/agents/{uid}/transcripts* — the agent's local conversations.

Two read-only surfaces over the ``.jsonl`` transcripts the agent itself wrote.
The **listing** is the browse table: title, project, message count, start and
last-activity times, plus the source path so a row can be opened on disk — and
deliberately no message text, because a list of a thousand sessions has no use
for it and carrying it would mean parsing every file for its bodies.

The **single-session read** is the other half, added when clicking a row started
opening that conversation instead of a "⋯" menu. It is the first thing in Coffer
that puts a transcript *body* on the wire, which is why it is a separate
endpoint rather than a flag on the listing: the guarantee "no message text
crosses the wire" still holds for the listing, and everything that guards a body
— secret-scrubbing every turn, capping each turn's length, windowing the turns,
and refusing any path that is not this agent's own transcript — is concentrated
in the one route that needs it.

``ResourceNotFound`` maps to 404 through the central handlers; an agent type
with no known transcript layout is the caller's request going wrong, so it comes
back as ``BAD_REQUEST``. A path that is not this agent's transcript, or names a
file that is gone, is ``NOT_FOUND`` — the two are one answer on purpose, so a
caller cannot use the difference to probe what exists outside the sessions dir.

Neither route audits: spec agent-registry "Audit every agent lifecycle event"
exempts every workspace listing, and reading one of the listed items is the
same act at a smaller scale.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from coffer.domain.agent.transcripts import UnsupportedAgentTypeError
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.errors import error_response
from coffer.surfaces.http.workspace_dependencies import get_agent_transcript_service

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


class TranscriptSessionSummary(BaseModel):
    """One transcript session as the list shows it."""

    session_id: str
    title: str | None = None
    project_path: str | None = None
    message_count: int
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    #: Absolute path of the ``.jsonl`` file, so the row can open/reveal it.
    source_path: str


class TranscriptMessageOut(BaseModel):
    """One conversational turn, as the session page renders it."""

    role: str
    #: Secret-scrubbed, and cut to the per-turn cap when ``truncated`` is true.
    text: str
    timestamp: datetime | None = None
    truncated: bool = False


class TranscriptSessionDetailResponse(BaseModel):
    """Response for GET /api/v1/agents/{uid}/transcripts/session.

    The summary fields are the listing's, so a page reached by deep link shows
    the same title and project the row did. ``message_count`` is the WHOLE
    file's turn count while ``messages`` is the ``limit`` turns from
    ``offset`` — a reader must be able to tell "200 of 812" from "all 200".
    """

    session_id: str
    title: str | None = None
    project_path: str | None = None
    message_count: int
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    source_path: str
    messages: list[TranscriptMessageOut]
    limit: int
    offset: int


class TranscriptSessionListResponse(BaseModel):
    """Response for GET /api/v1/agents/{uid}/transcripts.

    ``sessions`` is one page; ``total`` is the number of sessions matching the
    search/filter, so the UI can page and show "N of total".
    """

    sessions: list[TranscriptSessionSummary]
    total: int
    limit: int
    offset: int


@router.get("/{uid}/transcripts", response_model=TranscriptSessionListResponse)
async def list_transcripts(
    uid: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Search title or project path."),
    project: str | None = Query(None, description="Filter to this exact project_path."),
    sort: str = Query("last_activity_at", pattern="^(started_at|last_activity_at|message_count)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    svc: Any = Depends(get_agent_transcript_service),  # noqa: B008
) -> TranscriptSessionListResponse:
    """List an agent's transcript sessions with search, filter, and sort.

    Searches title + project path (``q``), filters by exact ``project``, and
    sorts by ``sort``/``order``. Backed by the reader's mtime-aware cache, so an
    agent with thousands of past sessions stays responsive. Paged by
    ``limit``/``offset`` against the matched total.
    """
    try:
        total, sessions = await svc.list_sessions(
            uid,
            limit=limit,
            offset=offset,
            query=q,
            project=project,
            sort=sort,
            order=order,
        )
    except UnsupportedAgentTypeError as exc:
        return error_response(  # type: ignore[return-value]
            "BAD_REQUEST",
            f"agent type not supported for transcript listing: {exc}",
        )

    return TranscriptSessionListResponse(
        sessions=[
            TranscriptSessionSummary(
                session_id=s.session_id,
                title=s.title,
                project_path=s.project_path,
                message_count=s.message_count,
                started_at=s.started_at,
                last_activity_at=s.last_activity_at,
                source_path=s.source_path,
            )
            for s in sessions
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{uid}/transcripts/session", response_model=TranscriptSessionDetailResponse)
async def read_transcript_session(
    uid: str,
    path: str = Query(description="Absolute source_path of a session, as the listing gave it."),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    svc: Any = Depends(get_agent_transcript_service),  # noqa: B008
) -> TranscriptSessionDetailResponse:
    """Render one of the agent's conversations: its summary and a page of turns.

    Bounded twice over, because a single transcript can be tens of megabytes:
    at most ``limit`` turns come back (500 ceiling), and each turn's text is cut
    at the domain's per-turn cap with ``truncated`` set. Every turn is
    secret-scrubbed before it leaves the parser — a prompt is where a pasted key
    would be. ``path`` must resolve inside this agent's own sessions directory;
    anything else is 404 rather than a file read.
    """
    try:
        body = await svc.read_session(uid, source_path=path, limit=limit, offset=offset)
    except UnsupportedAgentTypeError as exc:
        return error_response(  # type: ignore[return-value]
            "BAD_REQUEST",
            f"agent type not supported for transcript reading: {exc}",
        )
    except (ValueError, FileNotFoundError):
        return error_response(  # type: ignore[return-value]
            "NOT_FOUND",
            "no such transcript for this agent",
        )

    session = body.session
    return TranscriptSessionDetailResponse(
        session_id=session.session_id,
        title=session.title,
        project_path=session.project_path,
        message_count=session.message_count,
        started_at=session.started_at,
        last_activity_at=session.last_activity_at,
        source_path=session.source_path,
        messages=[
            TranscriptMessageOut(
                role=m.role,
                text=m.text,
                timestamp=m.timestamp,
                truncated=m.truncated,
            )
            for m in body.messages
        ],
        limit=body.limit,
        offset=body.offset,
    )
