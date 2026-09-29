"""MCP invocation log query routes — one server's calls, and all of them."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query

from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.capability import MCPInvocation
from coffer.domain.pagination import Page, decode_cursor, paginate, position_of, time_and_id
from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.log_schemas import InvocationListOut, InvocationOut
from coffer.surfaces.http.mcp.dependencies import get_invocation_repo, require_mcp_server

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


_CURSOR_HELP = (
    "The previous page's next_cursor. Bound to the filters it was issued with; "
    "any other value is 400 CURSOR_INVALID."
)


async def _page(
    repo: MCPInvocationRepo,
    *,
    resource_uid: str | None,
    status: Literal["ok", "error", "timeout", "denied"] | None,
    since: datetime | None,
    limit: int,
    cursor: str | None,
) -> Page[MCPInvocation]:
    """One newest-first page, continued by ``cursor`` (spec resource-framework
    "Page growing lists by an opaque cursor").

    The per-server route and the cross-server one narrowed to that server read
    the same rows in the same order, so they share one list tag: the filters,
    not the path, are what a cursor is bound to.
    """
    filters = {
        "resource_uid": resource_uid,
        "status": status,
        "since": since.isoformat() if since else None,
    }
    tag = "mcp_invocations"
    after = time_and_id(decode_cursor(cursor, list_tag=tag, filters=filters), int)
    rows = await repo.query(
        resource_uid=resource_uid, status=status, since=since, limit=limit + 1, after=after
    )
    return paginate(
        rows, limit, list_tag=tag, filters=filters, key=lambda r: position_of(r.timestamp, r.id)
    )


async def _project(
    page: Page[MCPInvocation],
    resources: ResourceService,
) -> InvocationListOut:
    """Turn log rows into the wire shape, attaching each server's current label.

    The log records the uid (ADR resource-identity-is-an-immutable-uid), which
    is what keeps one server's history one history across a rename — but a
    timeline of opaque uids is unreadable, and making every client hold the
    whole resource list just to render it would push this join into four
    different surfaces. So the name is resolved here, at read time.

    Resolution is ONE query for the whole page, not one per row: the mcp_server
    rows are fetched once into a uid → name map. A page of 500 invocations
    hitting a handful of servers would otherwise be 500 lookups of the same few
    rows.

    ``resource_name`` is null for a uid that resolves to nothing, which is the
    honest answer for the two reserved forms the log also carries — ``coffer``
    for Coffer's own built-in tools, ``deleted:<name>`` for a server already
    gone when the log was re-keyed — as well as for a server deleted since. The
    client falls back to showing the uid's own text there.

    The consequence of resolving rather than storing: a renamed server's past
    rows all read under its CURRENT name. That is the deliberate trade. The
    label is presentation, and presenting the name the user uses today beats
    presenting one they have already stopped using.
    """
    rows: Sequence[MCPInvocation] = page.items
    if not rows:
        return InvocationListOut(invocations=[], next_cursor=None)
    names_by_uid = {r.uid: r.name for r in await resources.list(kind="mcp_server")}
    return InvocationListOut(
        invocations=[
            InvocationOut(
                timestamp=r.timestamp,
                resource_uid=r.resource_uid,
                resource_name=names_by_uid.get(r.resource_uid),
                capability_type=r.capability_type,
                capability_key=r.capability_key,
                duration_ms=r.duration_ms,
                status=r.status,
                error_message=r.error_message,
                session_id=r.session_id,
            )
            for r in rows
        ],
        next_cursor=page.next_cursor,
    )


@router.get("/{uid}/invocations", response_model=InvocationListOut)
async def list_invocations(
    uid: str,
    since: datetime | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=500),
    cursor: str | None = Query(default=None, description=_CURSOR_HELP),
    status_filter: Literal["ok", "error", "timeout", "denied"] | None = Query(
        default=None, alias="status"
    ),
    repo: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> InvocationListOut:
    """Query invocation records for this server with optional filters.

    Resolves the uid first so an unknown server is a 404 rather than an empty
    list — "this server has made no calls" and "there is no such server" are
    different answers, and the resource page needs to tell them apart.
    """
    resource = await require_mcp_server(uid, resource_service)
    page = await _page(
        repo,
        resource_uid=resource.uid,
        status=status_filter,
        since=since,
        limit=limit,
        cursor=cursor,
    )
    return await _project(page, resource_service)


@aggregate_router.get("/invocations", response_model=InvocationListOut)
async def list_all_invocations(
    uid: str | None = Query(default=None),
    since: datetime | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=500),
    cursor: str | None = Query(default=None, description=_CURSOR_HELP),
    status_filter: Literal["ok", "error", "timeout", "denied"] | None = Query(
        default=None, alias="status"
    ),
    repo: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> InvocationListOut:
    """Every server's invocations on one timeline, newest-first.

    ``uid`` narrows to a single server, which makes this a superset of the
    per-server route; that one stays because the resource page addresses its
    own server by path, not by filter. The filter takes the value the rows were
    written under, so the two reserved forms (``coffer`` and ``deleted:<name>``)
    are filterable too — and, unlike the name filter this replaced, it neither
    hides the history of a server that has since been renamed nor hands a
    reused name the previous holder's calls.

    Unknown uids are NOT rejected here: this is a filter over a log, not an
    address for a resource, and the rows it can legitimately select include
    those belonging to servers that no longer exist.
    """
    page = await _page(
        repo, resource_uid=uid, status=status_filter, since=since, limit=limit, cursor=cursor
    )
    return await _project(page, resource_service)
