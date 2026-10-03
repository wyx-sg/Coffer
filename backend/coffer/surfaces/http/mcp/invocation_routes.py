"""MCP invocation log query routes — one server's calls, and all of them."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query

from coffer.application.mcp.invocation_outcome import is_upstream_answered
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.capability import MCPInvocation
from coffer.domain.pagination import Page, decode_cursor, paginate, position_of, time_and_id
from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.handoff_schemas import handoff_out
from coffer.surfaces.http.log_schemas import InvocationListOut, InvocationOut
from coffer.surfaces.http.mcp.dependencies import get_invocation_repo, require_mcp_server
from coffer.surfaces.http.mcp.handoff_views import call_failure_prompt

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

_STATUS_HELP = (
    "One outcome, or ``failed`` for every outcome but ``ok`` (an error, a timeout or a denial)."
)
_AGENT_UID_HELP = (
    "Only the calls made by this agent's sessions — the uid its shim reported. "
    "Calls from a session that reported no agent match no value."
)
_Q_HELP = (
    "Free text, matched in any case against the tool, the error, the session, "
    "the outcome and the server's name."
)
_TRACE_ID_HELP = (
    "Only the calls made under this correlation id — one /mcp request's — the "
    "same id its audit rows and daemon log lines carry."
)


async def _uids_named(resources: ResourceService, text: str) -> list[str]:
    """The uids of the MCP servers whose name or title contains ``text``."""
    needle = text.lower()
    return [
        r.uid
        for r in await resources.list(kind="mcp_server")
        if needle in r.name.lower() or needle in (r.title or "").lower()
    ]


async def _page(
    repo: MCPInvocationRepo,
    *,
    resource_uid: str | None,
    status: Literal["ok", "error", "timeout", "denied", "failed"] | None,
    since: datetime | None,
    agent_uid: str | None,
    limit: int,
    cursor: str | None,
    trace_id: str | None = None,
    q: str | None = None,
    q_resources: ResourceService | None = None,
) -> tuple[Page[MCPInvocation], int]:
    """One newest-first page, continued by ``cursor`` (spec resource-framework
    "Page growing lists by an opaque cursor").

    The per-server route and the cross-server one narrowed to that server read
    the same rows in the same order, so they share one list tag: the filters,
    not the path, are what a cursor is bound to.

    Returns the page and ``total`` — every row the filters match, across every
    page (spec resource-framework "Count a log's matching rows beside each
    page"). The cursor is decoded first, so a refused one costs no count.
    """
    filters = {
        "resource_uid": resource_uid,
        "status": status,
        "since": since.isoformat() if since else None,
        "agent_uid": agent_uid,
        "trace_id": trace_id,
        "q": q,
    }
    tag = "mcp_invocations"
    # The log stores a server's uid, the page shows its current name: a search
    # for a server's name finds its calls through the uids that name matches.
    q_uids = await _uids_named(q_resources, q) if q and q_resources is not None else ()
    after = time_and_id(decode_cursor(cursor, list_tag=tag, filters=filters), int)
    rows = await repo.query(
        resource_uid=resource_uid,
        status=status,
        since=since,
        agent_uid=agent_uid,
        limit=limit + 1,
        after=after,
        trace_id=trace_id,
        q=q,
        q_resource_uids=q_uids,
    )
    total = await repo.count(
        resource_uid=resource_uid,
        status=status,
        since=since,
        agent_uid=agent_uid,
        trace_id=trace_id,
        q=q,
        q_resource_uids=q_uids,
    )
    page = paginate(
        rows, limit, list_tag=tag, filters=filters, key=lambda r: position_of(r.timestamp, r.id)
    )
    return page, total


def _unanswered(r: MCPInvocation) -> bool:
    """A call the server never answered — refused, timed out, would not start —
    as opposed to one it answered with its own error or one Coffer denied."""
    return r.status == "timeout" or (r.status == "error" and not is_upstream_answered(r))


async def _failures_24h(repo: MCPInvocationRepo, uid: str) -> int:
    """How many calls to one server failed (error or timeout) in the last 24 hours."""
    since = datetime.now(tz=UTC) - timedelta(hours=24)
    return sum(
        [await repo.count(resource_uid=uid, status=s, since=since) for s in ("error", "timeout")]
    )


async def _project(
    page: Page[MCPInvocation],
    total: int,
    resources: ResourceService,
    repo: MCPInvocationRepo,
) -> InvocationListOut:
    """Turn log rows into the wire shape, attaching each server's current label.

    The log records the uid (ADR identity-is-the-uid-inside-the-file), which
    is what keeps one server's history one history across a rename — but a
    timeline of opaque uids is unreadable, and making every client hold the
    whole resource list just to render it would push this join into four
    different surfaces. So the name is resolved here, at read time.

    Resolution is ONE query for the whole page, not one per row: the mcp_server
    rows are fetched once into a uid → name map. A page of 500 invocations
    hitting a handful of servers would otherwise be 500 lookups of the same few
    rows.

    ``resource_name`` is null for a uid that resolves to nothing, which is the
    honest answer for ``coffer``, the reserved value Coffer's own built-in tools
    log under, and for a server deleted since. The client falls back to showing
    the uid's own text there.

    The consequence of resolving rather than storing: a renamed server's past
    rows all read under its CURRENT name. That is the deliberate trade. The
    label is presentation, and presenting the name the user uses today beats
    presenting one they have already stopped using.
    """
    rows: Sequence[MCPInvocation] = page.items
    if not rows:
        return InvocationListOut(invocations=[], next_cursor=None, total=total)
    names_by_uid = {r.uid: r.name for r in await resources.list(kind="mcp_server")}
    # A hand-off quotes how often the server failed today: one count per
    # server with an unanswered call on this page, not one per row.
    failures = {
        uid: await _failures_24h(repo, uid)
        for uid in {r.resource_uid for r in rows if _unanswered(r)}
    }

    def handoff_for(r: MCPInvocation) -> str | None:
        if not _unanswered(r):
            return None
        return call_failure_prompt(
            server=names_by_uid.get(r.resource_uid) or r.resource_uid,
            tool=r.capability_key,
            error=r.error_message,
            status=r.status,
            failures_24h=failures[r.resource_uid],
            session_id=r.session_id,
            call_id=r.id or 0,
        )

    return InvocationListOut(
        invocations=[
            InvocationOut(
                # Every row read back from the table has its id.
                id=r.id or 0,
                timestamp=r.timestamp,
                resource_uid=r.resource_uid,
                resource_name=names_by_uid.get(r.resource_uid),
                capability_type=r.capability_type,
                capability_key=r.capability_key,
                duration_ms=r.duration_ms,
                status=r.status,
                error_message=r.error_message,
                session_id=r.session_id,
                trace_id=r.trace_id,
                agent_uid=r.agent_uid,
                handoff=handoff_out(handoff_for(r)),
            )
            for r in rows
        ],
        next_cursor=page.next_cursor,
        total=total,
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
    agent_uid: str | None = Query(default=None, description=_AGENT_UID_HELP),
    trace_id: str | None = Query(default=None, description=_TRACE_ID_HELP),
    repo: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> InvocationListOut:
    """Query invocation records for this server with optional filters.

    Resolves the uid first so an unknown server is a 404 rather than an empty
    list — "this server has made no calls" and "there is no such server" are
    different answers, and the resource page needs to tell them apart.
    """
    resource = await require_mcp_server(uid, resource_service)
    page, total = await _page(
        repo,
        resource_uid=resource.uid,
        status=status_filter,
        since=since,
        agent_uid=agent_uid,
        limit=limit,
        cursor=cursor,
        trace_id=trace_id,
    )
    return await _project(page, total, resource_service, repo)


@aggregate_router.get("/invocations", response_model=InvocationListOut)
async def list_all_invocations(
    uid: str | None = Query(default=None),
    since: datetime | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=500),
    cursor: str | None = Query(default=None, description=_CURSOR_HELP),
    status_filter: Literal["ok", "error", "timeout", "denied", "failed"] | None = Query(
        default=None, alias="status", description=_STATUS_HELP
    ),
    agent_uid: str | None = Query(default=None, description=_AGENT_UID_HELP),
    trace_id: str | None = Query(default=None, description=_TRACE_ID_HELP),
    q: str | None = Query(default=None, description=_Q_HELP),
    repo: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> InvocationListOut:
    """Every server's invocations on one timeline, newest-first.

    ``uid`` narrows to a single server, which makes this a superset of the
    per-server route; that one stays because the resource page addresses its
    own server by path, not by filter. The filter takes the value the rows were
    written under, so the reserved ``coffer`` value is filterable too — and, unlike
    the name filter this replaced, it neither
    hides the history of a server that has since been renamed nor hands a
    reused name the previous holder's calls.

    Unknown uids are NOT rejected here: this is a filter over a log, not an
    address for a resource, and the rows it can legitimately select include
    those belonging to servers that no longer exist.
    """
    page, total = await _page(
        repo,
        resource_uid=uid,
        status=status_filter,
        since=since,
        agent_uid=agent_uid,
        limit=limit,
        cursor=cursor,
        trace_id=trace_id,
        q=q or None,
        q_resources=resource_service,
    )
    return await _project(page, total, resource_service, repo)
