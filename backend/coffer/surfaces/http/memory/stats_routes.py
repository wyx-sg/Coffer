"""The Memory page's delivered view (spec memory "Show what each agent is given
at session start").

``GET /memory/partitions/{uid}/delivered`` — the exact session-start text each
agent gets in that partition's repository.

It carries nothing about whether a hook is installed or trusted; that is the
agent's page.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.memory.delivery_stats import DeliveryStatsService
from coffer.application.memory.partition_row import placement_of
from coffer.application.resource_service import ResourceService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.memory.delivery_schemas import (
    DeliveredOut,
    DeliveredTextOut,
)
from coffer.surfaces.http.memory.dependencies import get_memory_stats_service
from coffer.surfaces.http.memory.lookup import require_partition

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
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
