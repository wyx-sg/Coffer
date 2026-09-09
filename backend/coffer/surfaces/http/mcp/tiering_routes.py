"""Read-only view of the ADR-046 tool-tiering decision.

Its own router (not ``/resources/mcp_server/...``) because the decision is
global across every enabled server: reporting it per server would give the
wrong answer, since a server whose ten tools all fit locally can still be
crowded out of the shared budget.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from coffer.application.mcp.tiering_config import load_tiering_config
from coffer.application.mcp.tiering_report import build_tiering_report
from coffer.application.resource_service import ResourceService
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
)
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_invocation_repo,
    get_preferences_repo,
    get_resource_service,
)
from coffer.surfaces.http.schemas import ToolTieringOut, ToolTieringServerOut

router = APIRouter(
    prefix="/api/v1/mcp",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


@router.get("/tiering", response_model=ToolTieringOut)
async def get_tool_tiering(
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    invocations: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
) -> ToolTieringOut:
    """How much of the aggregated catalogue agents currently see.

    Computed from the last-discovered catalogue, so it never cold-spawns an
    upstream to answer a management question.
    """
    report = await build_tiering_report(
        resources=resources,
        prefs=prefs,
        invocations=invocations,
        config=load_tiering_config(),
        clock=lambda: datetime.now(tz=UTC),
    )
    return ToolTieringOut(
        enabled=report.enabled,
        budget=report.budget,
        window_days=report.window_days,
        total=report.total,
        listed=report.listed,
        hidden=report.hidden,
        servers=[
            ToolTieringServerOut(server=s.server, total=s.total, listed=s.listed)
            for s in report.servers
        ],
    )
