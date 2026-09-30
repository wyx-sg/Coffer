"""The MCP server page's reads beside status.

The last 24 hours, the server's own log, and the tiering split.

Each addresses its server by uid (``require_mcp_server``) and reads persisted
state only — the invocation log, the upstream's log file, the tool lists
discovery saved — so opening a server's page never spawns it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from coffer.application.mcp.tiering_config import load_tiering_config
from coffer.application.mcp.tiering_split import tiering_split
from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Resource
from coffer.infrastructure.logging.upstream_tail import read_upstream_tail
from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceStore, MCPInvocationRepo
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.mcp.dependencies import (
    get_invocation_repo,
    get_preferences_repo,
    require_mcp_server,
)
from coffer.surfaces.http.mcp.page_schemas import (
    InvocationSummaryOut,
    McpServerLogLineOut,
    McpServerLogOut,
    ToolTieringOut,
    invocation_summary_out,
)

#: The seen-time of a capability this machine has never seen (see
#: ``MCPCapabilityPreferenceStore.list_for``).
_NEVER_SEEN = datetime.fromtimestamp(0, tz=UTC)

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


@router.get("/{uid}/invocations/summary", response_model=InvocationSummaryOut)
async def invocation_summary(
    uid: str,
    since: datetime | None = Query(  # noqa: B008
        default=None, description="Count calls at or after this moment; default 24 hours ago."
    ),
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    invocations: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
) -> InvocationSummaryOut:
    """This server's calls since ``since``: totals, per calling agent, per tool."""
    resource = await require_mcp_server(uid, resource_service)
    start = since or datetime.now(tz=UTC) - timedelta(hours=24)
    summary = await invocations.summary(resource_uid=resource.uid, since=start)
    return invocation_summary_out(summary)


@router.get("/{uid}/log", response_model=McpServerLogOut)
async def server_log(
    uid: str,
    limit: int = Query(default=200, ge=1, le=2000),
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> McpServerLogOut:
    """The newest lines of the server's own log file: its stderr, and Coffer's
    lines about starting and stopping it. A server Coffer does not start (HTTP)
    has none."""
    resource = await require_mcp_server(uid, resource_service)
    transport = resource.config.get("transport")
    if not isinstance(transport, dict) or transport.get("type") != "stdio":
        return McpServerLogOut()
    tail = await asyncio.to_thread(read_upstream_tail, resource.name, limit)
    return McpServerLogOut(
        path=str(tail.path) if tail.path is not None else None,
        lines=[
            McpServerLogLineOut(text=line.text, source=line.source, at=line.at)  # type: ignore[arg-type]
            for line in tail.lines
        ],
        truncated=tail.truncated,
    )


async def _current_tools(
    prefs: MCPCapabilityPreferenceStore, resource: Resource
) -> list[tuple[str, bool]]:
    """The tools discovery last saw for ``resource``, with their switch.

    Every rediscovery stamps each tool it still sees with one ``last_seen_at``;
    rows for tools the server no longer offers keep an older stamp, so the
    current set is the rows carrying the newest one. A tool switched off on
    another machine and never seen here has no stamp, and is not current.
    """
    rows = [r for r in await prefs.list_for(resource.uid, "tool") if r.last_seen_at > _NEVER_SEEN]
    if not rows:
        return []
    newest = max(r.last_seen_at for r in rows)
    return [(r.capability_key, r.enabled) for r in rows if r.last_seen_at == newest]


@router.get("/{uid}/tiering", response_model=ToolTieringOut)
async def tool_tiering(
    uid: str,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceStore = Depends(get_preferences_repo),  # noqa: B008
    invocations: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
) -> ToolTieringOut:
    """Which of this server's tools are listed to agents and which only reached through search."""
    resource = await require_mcp_server(uid, resource_service)
    own = await _current_tools(prefs, resource)
    catalogue: dict[str, list[str]] = {}
    for server in await resource_service.list(kind="mcp_server", enabled=True):
        tools = own if server.uid == resource.uid else await _current_tools(prefs, server)
        catalogue[server.name] = [name for name, on in tools if on]
    split = await tiering_split(
        catalogue,
        resource.name,
        invocations=invocations,
        config=load_tiering_config(),
        clock=lambda: datetime.now(tz=UTC),
    )
    return ToolTieringOut(
        enabled=split.enabled,
        budget=split.budget,
        catalogue_size=split.catalogue_size,
        listed_count=split.listed_count,
        tool_count=len(own),
        listed=split.listed,
        behind_search=split.behind_search,
    )
