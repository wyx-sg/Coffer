"""MCP invocation log query routes — one server's calls, and all of them."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query

from coffer.domain.mcp.capability import MCPInvocation
from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_invocation_repo
from coffer.surfaces.http.schemas import InvocationListOut, InvocationOut

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)

# The cross-server view is not about one resource, so it does not belong under
# the per-resource prefix. Same file because it is the same query and the same
# projection — only the scope differs.
aggregate_router = APIRouter(
    prefix="/api/v1/mcp",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


def _to_out(r: MCPInvocation) -> InvocationOut:
    return InvocationOut(
        timestamp=r.timestamp,
        resource_name=r.resource_name,
        capability_type=r.capability_type,
        capability_key=r.capability_key,
        duration_ms=r.duration_ms,
        status=r.status,
        error_message=r.error_message,
        session_id=r.session_id,
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
    return InvocationListOut(invocations=[_to_out(r) for r in rows])


@aggregate_router.get("/invocations", response_model=InvocationListOut)
async def list_all_invocations(
    name: str | None = Query(default=None),
    since: datetime | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=500),
    status_filter: Literal["ok", "error", "timeout", "denied"] | None = Query(
        default=None, alias="status"
    ),
    repo: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
) -> InvocationListOut:
    """Every server's invocations on one timeline, newest-first.

    ``name`` narrows to a single server, which makes this a superset of the
    per-server route; that one stays because the resource page addresses its
    own server by path, not by filter.
    """
    rows = await repo.query(resource_name=name, status=status_filter, since=since, limit=limit)
    return InvocationListOut(invocations=[_to_out(r) for r in rows])
