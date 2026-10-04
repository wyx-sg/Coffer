"""``/api/v1/memory/partitions`` and the one action that rewrites the tree.

The list a management surface starts from, and ``POST /sync`` (Update memory:
aggregation, which is corpus-wide, then distil over every partition it left
new). Grouped together because ``/sync`` is the family's *write* half:
everything else under this prefix reads. There is no per-partition trigger:
Update memory already distils every partition that gained entries, and skips
one whose pass is running ("Run one distil pass per partition at a time").

Partition deletion is deliberately absent — it goes through the kind-agnostic
``DELETE /api/v1/resources/{uid}``, exactly like knowledge's collections, since
lifecycle is a Resource concern and not this kind's own.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.memory.service import MemoryService
from coffer.application.memory.update import update_memory
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.memory.dependencies import get_memory_service
from coffer.surfaces.http.memory.schemas import (
    AggregationResultOut,
    PartitionListOut,
    PartitionOut,
)

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)


@router.get("/partitions", response_model=PartitionListOut)
async def list_partitions(
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> PartitionListOut:
    found = await svc.list_partitions()
    return PartitionListOut(
        partitions=[
            PartitionOut(
                # The identity every other route on this family takes, so a
                # surface that has listed the partitions never has to look one
                # up by label to act on it.
                uid=p.uid,
                name=p.name,
                repository_key=p.repository_key,
                repository_path=p.repository_path,
                note_count=p.note_count,
                unresolvable=p.unresolvable,
                distilled_at=p.distilled_at,
                sources=list(p.sources),
                waiting_entries=p.waiting_entries,
                waiting_agents=list(p.waiting_agents),
                updated_at=p.updated_at,
            )
            for p in found
        ]
    )


@router.post("/sync", response_model=AggregationResultOut)
async def sync(
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> AggregationResultOut:
    """Update memory: aggregate every registered agent's native
    memory, then distil every partition it left with undistilled raw entries
    ("Update memory in one action"; see ``application/memory/update.py``).

    The actor travels in so the ``memory_aggregated`` and ``memory_distilled``
    events the service records distinguish this requested update from the
    workers' scheduled passes.
    """
    outcome = await update_memory(svc, actor=actor)
    result = outcome.aggregation
    return AggregationResultOut(
        partitions=list(result.partitions),
        entries_written=result.entries_written,
        sources_read=result.sources_read,
        sources_skipped=result.sources_skipped,
        failures=[f.path for f in result.failures],
        distilled=list(outcome.distilled),
        skipped=list(outcome.skipped),
    )
