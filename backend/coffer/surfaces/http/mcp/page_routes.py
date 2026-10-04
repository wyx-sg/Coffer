"""The MCP server page's reads beside status.

The last 24 hours, the server's own log, the tiering split and how each tool is exposed.

Each addresses its server by uid (``require_mcp_server``) and reads persisted
state only — the invocation log, the upstream's log file, the tool lists
discovery saved — so opening a server's page never spawns it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status

from coffer.application.audit_service import AuditService
from coffer.application.mcp.saved_tools import current_tools
from coffer.application.mcp.tiering_config import load_tiering_config
from coffer.application.mcp.tiering_split import tiering_split
from coffer.application.mcp.tool_exposure import exposure_overrides
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.infrastructure.logging.upstream_tail import read_upstream_tail
from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceStore, MCPInvocationRepo
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service, get_resource_service
from coffer.surfaces.http.mcp.dependencies import (
    get_invocation_repo,
    get_preferences_repo,
    require_mcp_server,
)
from coffer.surfaces.http.mcp.page_schemas import (
    InvocationSummaryOut,
    McpServerLogLineOut,
    McpServerLogOut,
    ToolExposureBatchBody,
    ToolExposureBody,
    ToolExposureOut,
    ToolTieringOut,
    invocation_summary_out,
)

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


@router.get("/{uid}/tiering", response_model=ToolTieringOut)
async def tool_tiering(
    uid: str,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceStore = Depends(get_preferences_repo),  # noqa: B008
    invocations: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
) -> ToolTieringOut:
    """Which of this server's tools are listed to agents and which only reached through search."""
    resource = await require_mcp_server(uid, resource_service)
    own = await current_tools(prefs, resource)
    catalogue: dict[str, list[str]] = {}
    servers = await resource_service.list(kind="mcp_server", enabled=True)
    for server in servers:
        tools = own if server.uid == resource.uid else await current_tools(prefs, server)
        catalogue[server.name] = [name for name, on in tools if on]
    split = await tiering_split(
        catalogue,
        resource.name,
        invocations=invocations,
        config=load_tiering_config(),
        clock=lambda: datetime.now(tz=UTC),
        exposure=await exposure_overrides(prefs, servers),
    )
    return ToolTieringOut(
        enabled=split.enabled,
        budget=split.budget,
        catalogue_size=split.catalogue_size,
        listed_count=split.listed_count,
        tool_count=len(own),
        listed=split.listed,
        behind_search=split.behind_search,
        tools=[
            ToolExposureOut(
                tool=s.tool,
                mode=s.mode,
                effective=s.effective,
                reason=s.reason,
            )
            for s in split.tools
        ],
    )


async def _set_exposure(
    uid: str,
    changes: dict[str, str],
    *,
    resource_service: ResourceService,
    prefs: MCPCapabilityPreferenceStore,
    audit: AuditService,
    actor: str,
) -> Response:
    resource = await require_mcp_server(uid, resource_service)
    if not await prefs.set_exposure(resource.uid, changes):
        raise HTTPException(status_code=404, detail="tool not found on this server")
    modes = set(changes.values())
    await audit.record(
        AuditEventType.TOOL_EXPOSURE_CHANGED.value,
        resource=resource,
        actor=actor,
        details={
            "key": next(iter(changes)) if len(changes) == 1 else f"{len(changes)} tools",
            "tools": sorted(changes),
            "mode": modes.pop() if len(modes) == 1 else "mixed",
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{uid}/tools/{tool}/exposure",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def set_tool_exposure(
    uid: str,
    tool: str,
    body: ToolExposureBody = Body(...),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceStore = Depends(get_preferences_repo),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Set how one tool is exposed to agents: ``auto``, ``listed`` or ``search``."""
    return await _set_exposure(
        uid,
        {tool: body.mode},
        resource_service=resource_service,
        prefs=prefs,
        audit=audit,
        actor=actor,
    )


@router.patch(
    "/{uid}/tools/exposure",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def set_tools_exposure(
    uid: str,
    body: ToolExposureBatchBody = Body(...),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceStore = Depends(get_preferences_repo),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Set one exposure mode on several tools in one write; nothing changes if any is unknown."""
    return await _set_exposure(
        uid,
        dict.fromkeys(body.tools, body.mode),
        resource_service=resource_service,
        prefs=prefs,
        audit=audit,
        actor=actor,
    )
