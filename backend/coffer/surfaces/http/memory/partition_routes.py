"""``/api/v1/memory/partitions`` and the two passes that rewrite the tree.

The list a management surface starts from, ``POST /sync`` (aggregation, which
is corpus-wide) and ``POST /partitions/{uid}/distil`` (one partition at a
time). Grouped together because they are the family's *write* half: everything
else under this prefix reads.

Partition deletion is deliberately absent — it goes through the kind-agnostic
``DELETE /api/v1/resources/{uid}``, exactly like knowledge's collections, since
lifecycle is a Resource concern and not this kind's own.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.application.resource_service import ResourceService
from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_resource_service
from coffer.surfaces.http.memory.dependencies import get_memory_service
from coffer.surfaces.http.memory.distil_state import get_distil_runner
from coffer.surfaces.http.memory.lookup import require_partition
from coffer.surfaces.http.memory.schemas import (
    AggregationResultOut,
    DistilResultOut,
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
            )
            for p in found
        ]
    )


@router.post("/sync", response_model=AggregationResultOut)
async def sync(
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> AggregationResultOut:
    """Run aggregation over every registered, enabled agent's native memory.

    The actor travels in so the ``memory_aggregated`` event the service records
    distinguishes this requested pass from the worker's scheduled one.
    """
    result = await svc.aggregate(actor=actor)
    return AggregationResultOut(
        partitions=list(result.partitions),
        entries_written=result.entries_written,
        sources_read=result.sources_read,
        sources_skipped=result.sources_skipped,
        failures=[f.path for f in result.failures],
    )


@router.post("/partitions/{uid}/distil", response_model=DistilResultOut)
async def distil(
    uid: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> DistilResultOut:
    """Turn one partition's raw entries into notes, and rewrite its index."""
    # Resolved first so an unknown partition is a 404 BEFORE anything is
    # claimed; the row itself is not wanted here, because the pass resolves it
    # again for the directory it rewrites.
    await require_partition(uid, resources)
    # One pass per partition at a time. The pass takes minutes and rewrites the
    # whole partition directory, so a second request while one is in flight is
    # refused (409 ``UPKEEP_ALREADY_RUNNING``) rather than started: two of them
    # are two writers racing, not one faster pass. The registry is also what
    # `GET /api/v1/upkeep/runs` reads, so a surface that mounts mid-pass can
    # show the button as already running instead of inviting the second click.
    #
    # Keyed on the uid, which is exactly what the unattended sweep claims
    # (``distil_worker``): the collision "Run one distil pass per partition at a
    # time" needs only happens if both
    # writers spell the partition the same way, and a label is the one spelling
    # that can change between the two of them reading it.
    with UPKEEP_RUNS.guard(KIND_MEMORY, uid):
        result = await get_distil_runner()(uid, actor=actor)
    return DistilResultOut(
        partition=result.partition,
        merged=result.merged,
        opened=result.opened,
        retired=result.retired,
        dropped=result.dropped,
        model_used=result.model_used,
    )
