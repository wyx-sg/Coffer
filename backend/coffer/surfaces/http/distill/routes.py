"""/api/v1/agents/{name}/transcripts routes (Spec 007 extension — ADR-020).

Transcript-distillation surface: lists a registered agent's transcript sessions
and distils a selected session into Coffer memory facts via the LLM.

Domain errors are translated to the standard ``{error:{code,message,details}}``
envelope. The ``X-Coffer-Token`` / ``require_token`` guard and the
``X-Coffer-Actor`` header convention mirror sibling routers.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from coffer.application.distill.service import (
    NoModelConfiguredError,
    TranscriptDistillationService,
)
from coffer.domain.distill.locations import UnsupportedAgentTypeError
from coffer.domain.errors import ResourceNotFound
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.distill.schemas import (
    DistillRequest,
    DistillResponse,
    InsightOut,
    TranscriptSessionListResponse,
    TranscriptSessionSummary,
)
from coffer.surfaces.http.distill.state import get_distill_service
from coffer.surfaces.http.errors import error_response

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["transcripts"],
    dependencies=[Depends(require_token)],
)


@router.get(
    "/{name}/transcripts",
    response_model=TranscriptSessionListResponse,
)
async def list_transcripts(
    name: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Search title or project path."),
    project: str | None = Query(None, description="Filter to this exact project_path."),
    started_after: datetime | None = Query(  # noqa: B008
        None, description="Keep started_at ≥ this instant."
    ),
    started_before: datetime | None = Query(  # noqa: B008
        None, description="Keep started_at ≤ this instant."
    ),
    sort: str = Query("last_activity_at", pattern="^(started_at|last_activity_at|message_count)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    svc: TranscriptDistillationService = Depends(get_distill_service),  # noqa: B008
) -> TranscriptSessionListResponse:
    """List an agent's transcript sessions with search, filter, and sort.

    Searches title + project path (``q``), filters by exact ``project`` and a
    ``started_at`` range, and sorts by ``sort``/``order``. Backed by the
    reader's mtime-aware cache, so an agent with thousands of past sessions
    stays responsive. Paged by ``limit``/``offset`` against the matched total.
    """
    try:
        total, sessions = await svc.list_sessions(
            agent_name=name,
            limit=limit,
            offset=offset,
            query=q,
            project=project,
            started_after=started_after,
            started_before=started_before,
            sort=sort,
            order=order,
        )
    except ResourceNotFound:
        return error_response("RESOURCE_NOT_FOUND", f"agent {name!r} not found")  # type: ignore[return-value]
    except UnsupportedAgentTypeError as exc:
        return error_response(  # type: ignore[return-value]
            "UNSUPPORTED_AGENT_TYPE",
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


@router.post(
    "/{name}/transcripts/distill",
    response_model=DistillResponse,
)
async def distill_transcript(
    name: str,
    body: DistillRequest,
    svc: TranscriptDistillationService = Depends(get_distill_service),  # noqa: B008
) -> DistillResponse:
    """Distil a transcript session into Coffer memory facts."""
    try:
        result = await svc.distill(
            agent_name=name,
            session_id=body.session_id,
            project_path=body.project_path,
            dry_run=body.dry_run,
        )
    except ResourceNotFound:
        return error_response("RESOURCE_NOT_FOUND", f"agent {name!r} not found")  # type: ignore[return-value]
    except UnsupportedAgentTypeError as exc:
        return error_response(  # type: ignore[return-value]
            "UNSUPPORTED_AGENT_TYPE",
            f"agent type not supported for distillation: {exc}",
        )
    except NoModelConfiguredError as exc:
        return error_response("NO_MODEL_CONFIGURED", str(exc))  # type: ignore[return-value]
    except KeyError as exc:
        return error_response(  # type: ignore[return-value]
            "TRANSCRIPT_SESSION_NOT_FOUND",
            f"transcript session not found: {exc}",
        )
    except ValueError as exc:
        return error_response("BAD_REQUEST", str(exc))  # type: ignore[return-value]

    return DistillResponse(
        insights=[
            InsightOut(
                name=i.name,
                description=i.description,
                body=i.body,
                type=i.type,
            )
            for i in result.insights
        ],
        fact_ids=result.facts,
    )
