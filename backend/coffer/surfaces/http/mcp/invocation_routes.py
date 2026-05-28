"""MCP invocation log query route."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query

from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_invocation_repo
from coffer.surfaces.http.schemas import InvocationListOut, InvocationOut

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


@router.get("/{name}/invocations", response_model=InvocationListOut)
async def list_invocations(
    name: str,
    since: datetime | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=500),
    status_filter: Literal["ok", "error", "timeout", "denied"] | None = Query(
        default=None, alias="status"
    ),
    repo: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
) -> InvocationListOut:
    """Query invocation records for this server with optional filters."""
    rows = await repo.query(resource_name=name, status=status_filter, since=since, limit=limit)
    return InvocationListOut(
        invocations=[
            InvocationOut(
                timestamp=r.timestamp,
                capability_type=r.capability_type,
                capability_key=r.capability_key,
                duration_ms=r.duration_ms,
                status=r.status,
                error_message=r.error_message,
                session_id=r.session_id,
            )
            for r in rows
        ]
    )
