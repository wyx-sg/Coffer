"""The Memory page's delivery views (spec memory "Count what memory delivered
and what was read", "Show what each agent is given at session start").

``GET /memory/deliveries`` — per agent, over the last seven days: how often
memory reached it, by moment, when it last did, and how many distinct notes
its sessions opened. ``GET /memory/partitions/{uid}/delivered`` — the exact
session-start text each agent gets in that partition's repository.

Neither carries whether a hook is installed or trusted; that is the agent's
page.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.memory.delivery_stats import WINDOW_DAYS, DeliveryStatsService
from coffer.application.memory.partition_row import placement_of
from coffer.application.resource_service import ResourceService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.memory.delivery_schemas import (
    AgentDeliveryStatsOut,
    DeliveredOut,
    DeliveredTextOut,
    DeliveryOverviewOut,
)
from coffer.surfaces.http.memory.dependencies import get_memory_stats_service
from coffer.surfaces.http.memory.lookup import require_partition

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)


@router.get("/deliveries", response_model=DeliveryOverviewOut)
async def deliveries(
    svc: DeliveryStatsService = Depends(get_memory_stats_service),  # noqa: B008
) -> DeliveryOverviewOut:
    stats = await svc.overview(days=WINDOW_DAYS)
    return DeliveryOverviewOut(
        window_days=WINDOW_DAYS,
        agents=[
            AgentDeliveryStatsOut(
                agent_uid=s.agent_uid,
                agent_name=s.agent_name,
                agent_type=s.agent_type,
                deliveries=s.deliveries,
                by_moment=s.by_moment,
                last_delivered_at=s.last_delivered_at,
                notes_read=s.notes_read,
                notes_read_status="available" if s.notes_read is not None else "unavailable",
            )
            for s in stats
        ],
    )


@router.get("/partitions/{uid}/delivered", response_model=DeliveredOut)
async def delivered(
    uid: str,
    svc: DeliveryStatsService = Depends(get_memory_stats_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> DeliveredOut:
    row = await require_partition(uid, resources)
    texts = await svc.delivered(repository_path=placement_of(row).repository_path)
    return DeliveredOut(
        partition=row.name,
        agents=[
            DeliveredTextOut(
                agent_uid=t.agent_uid,
                agent_name=t.agent_name,
                agent_type=t.agent_type,
                event=t.event,
                text=t.text,
            )
            for t in texts
        ],
    )
