"""/api/v1/history routes — cross-agent transcript history (ADR-022).

Search and read-only browse over a local-only, rebuildable index of the in-place
agent ``.jsonl`` transcripts. Nothing here writes to an agent's session store or
to the sync medium. Errors map to the standard ``{error:{code,message}}``
envelope; the ``X-Coffer-Token`` guard mirrors sibling routers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from coffer.application.history.service import HistoryService
from coffer.domain.distill.locations import UnsupportedAgentTypeError
from coffer.domain.errors import ResourceNotFound
from coffer.domain.history.results import (
    HistorySearchHit,
    HistorySessionDetail,
    HistorySessionRef,
)
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.errors import error_response
from coffer.surfaces.http.history.schemas import (
    HistorySearchHitOut,
    HistorySearchResponse,
    HistorySessionDetailResponse,
    HistorySessionListResponse,
    HistorySessionSummary,
    HistoryTurnOut,
    RebuildResponse,
    ResetResponse,
)
from coffer.surfaces.http.history.state import get_history_service

router = APIRouter(
    prefix="/api/v1/history",
    tags=["history"],
    dependencies=[Depends(require_token)],
)


def _summary(ref: HistorySessionRef) -> HistorySessionSummary:
    return HistorySessionSummary(
        agent_type=ref.agent_type,
        session_id=ref.session_id,
        project_path=ref.project_path,
        started_at=ref.started_at,
        title=ref.title,
        message_count=ref.message_count,
    )


def _hit(hit: HistorySearchHit) -> HistorySearchHitOut:
    return HistorySearchHitOut(
        agent_type=hit.agent_type,
        session_id=hit.session_id,
        project_path=hit.project_path,
        started_at=hit.started_at,
        title=hit.title,
        snippet=hit.snippet,
        score=hit.score,
    )


@router.get("/search", response_model=HistorySearchResponse)
async def search_history(
    q: Annotated[str, Query(description="search query")],
    agent_type: Annotated[str | None, Query()] = None,
    project: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    svc: HistoryService = Depends(get_history_service),  # noqa: B008
) -> HistorySearchResponse:
    hits = await svc.search(q, agent_type=agent_type, project_path=project, limit=limit)
    return HistorySearchResponse(query=q, hits=[_hit(h) for h in hits])


@router.get("/sessions", response_model=HistorySessionListResponse)
async def list_sessions(
    agent: Annotated[str, Query(description="registered agent name")],
    svc: HistoryService = Depends(get_history_service),  # noqa: B008
) -> HistorySessionListResponse:
    try:
        refs = await svc.list_sessions(agent_name=agent)
    except ResourceNotFound:
        return error_response("RESOURCE_NOT_FOUND", f"agent {agent!r} not found")  # type: ignore[return-value]
    except UnsupportedAgentTypeError as exc:
        return error_response("UNSUPPORTED_AGENT_TYPE", str(exc))  # type: ignore[return-value]
    return HistorySessionListResponse(sessions=[_summary(r) for r in refs])


@router.get("/session", response_model=HistorySessionDetailResponse)
async def browse_session(
    agent: Annotated[str, Query(description="registered agent name")],
    session_id: Annotated[str, Query()],
    svc: HistoryService = Depends(get_history_service),  # noqa: B008
) -> HistorySessionDetailResponse:
    try:
        detail: HistorySessionDetail = await svc.browse(agent_name=agent, session_id=session_id)
    except ResourceNotFound:
        return error_response("RESOURCE_NOT_FOUND", f"agent {agent!r} not found")  # type: ignore[return-value]
    except UnsupportedAgentTypeError as exc:
        return error_response("UNSUPPORTED_AGENT_TYPE", str(exc))  # type: ignore[return-value]
    except KeyError as exc:
        return error_response("TRANSCRIPT_SESSION_NOT_FOUND", str(exc))  # type: ignore[return-value]
    return HistorySessionDetailResponse(
        session=_summary(detail.ref),
        turns=[HistoryTurnOut(role=t.role, text=t.text) for t in detail.turns],
    )


@router.post("/reindex", response_model=RebuildResponse)
async def reindex_history(
    agent: Annotated[str | None, Query(description="limit to one agent")] = None,
    svc: HistoryService = Depends(get_history_service),  # noqa: B008
) -> RebuildResponse:
    stats = await svc.rebuild(agent_name=agent)
    return RebuildResponse(indexed=stats.indexed, unchanged=stats.unchanged, removed=stats.removed)


@router.post("/reset", response_model=ResetResponse)
async def reset_history(
    svc: HistoryService = Depends(get_history_service),  # noqa: B008
) -> ResetResponse:
    removed = await svc.reset()
    return ResetResponse(removed=removed)
