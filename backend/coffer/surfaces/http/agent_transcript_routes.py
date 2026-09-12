"""GET /api/v1/agents/{name}/transcripts — the agent's local conversation list.

A read-only browse surface over the ``.jsonl`` transcripts the agent itself
wrote: title, project, message count, start and last-activity times, plus the
source path so the UI can offer open-in-editor / reveal. Nothing is written and
no message text crosses the wire.

``ResourceNotFound`` maps to 404 through the central handlers; an agent type
with no known transcript layout is the caller's request going wrong, so it comes
back as ``BAD_REQUEST``.
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


class TranscriptSessionListResponse(BaseModel):
    """Response for GET /api/v1/agents/{name}/transcripts.

    ``sessions`` is one page; ``total`` is the number of sessions matching the
    search/filter, so the UI can page and show "N of total".
    """

    sessions: list[TranscriptSessionSummary]
    total: int
    limit: int
    offset: int


@router.get("/{name}/transcripts", response_model=TranscriptSessionListResponse)
async def list_transcripts(
    name: str,
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
            name,
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
