"""``/api/v1/memory/*`` — the human's side of the memory layer (spec memory
FR-061).

List partitions and facts, show one fact with its origins and conflicts, run
a sync, run an organise pass, compose the session context, apply and clear
each of the four overrides, and install/inspect/remove delivery for an agent.
Partition deletion goes through the kind-agnostic Resource route (``DELETE
/api/v1/resources/memory/{name}``), exactly like knowledge's collections —
lifecycle is a Resource concern, not this kind's own.

Like knowledge's REST surface, these routes are the *owner's* view and are
therefore unscoped: ``list_facts``/``list_partitions`` are called with no
``agent``, so nothing here is filtered by a Resource's scope. Scope IS
enforced on the one route a real agent's own session actually reaches —
``POST /context`` composes ``MemoryService.visible_partitions(agent)``
underneath (``application.memory.context.compose_context``) — and on
``coffer__recall`` (FR-052), which this surface does not expose at all: L2
is MCP-only (FR-060).

Every override change and every organise pass is audited here (FR-063):
``organise_partition`` and ``OverrideRepository`` are both pure/persistence
layers with no ``AuditService`` of their own (by design — see
``memory_wiring.py`` and ``application/memory/overrides.py``'s module
docstrings), so the record is made at this boundary instead. Aggregation and
delivery install/remove already audit themselves inside their own services.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Depends, Query

from coffer.application.audit_service import AuditService
from coffer.application.memory.context import DEFAULT_BUDGET_TOKENS, compose_context
from coffer.application.memory.overrides import Override
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.fact import Fact
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.memory.store import FactNotFound
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_actor,
    get_audit_service,
    get_resource_service,
)
from coffer.surfaces.http.memory.dependencies import (
    get_memory_delivery_service,
    get_memory_override_repo,
    get_memory_service,
)
from coffer.surfaces.http.memory.organise_state import get_organise_runner
from coffer.surfaces.http.memory.schemas import (
    AggregationResultOut,
    ComposedContextOut,
    ContextQuery,
    DeliveryStatusListOut,
    DeliveryStatusOut,
    FactListOut,
    FactOut,
    FactSummaryOut,
    OrganiseResultOut,
    OriginOut,
    OverrideListOut,
    OverrideOut,
    OverridePatch,
    PartitionListOut,
    PartitionOut,
)

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)

_EVENT_ORGANISED = AuditEventType.MEMORY_ORGANISED.value
_EVENT_OVERRIDE_SET = AuditEventType.MEMORY_OVERRIDE_SET.value
_EVENT_OVERRIDE_CLEARED = AuditEventType.MEMORY_OVERRIDE_CLEARED.value

_actor = get_actor


async def _require_partition(name: str, resources: ResourceService) -> None:
    """404 (``RESOURCE_NOT_FOUND``) for a partition no ``memory`` Resource
    names — the generic, already-mapped error, since inventing a memory-
    specific "no such partition" code would duplicate it for no reason."""
    await resources.get(ResourceRef(KIND_MEMORY, name))


def _override_out(override: Override) -> OverrideOut:
    return OverrideOut(
        fact_key=override.fact_key,
        hidden=override.hidden,
        pinned=override.pinned,
        superseded_by=override.superseded_by,
        conflict_choice=override.conflict_choice,
    )


def _fact_summary(fact: Fact, overrides: dict[str, Override]) -> FactSummaryOut:
    override = overrides.get(fact.key)
    return FactSummaryOut(
        key=fact.key,
        slug=fact.slug,
        partition=fact.partition,
        title=fact.title,
        description=fact.description,
        type=fact.type,
        status=fact.status,
        superseded_by=fact.superseded_by,
        conflicts_with=list(fact.conflicts_with),
        proposed=fact.proposed,
        hidden=bool(override and override.hidden),
        pinned=bool(override and override.pinned),
    )


def _fact_out(fact: Fact, overrides: dict[str, Override]) -> FactOut:
    summary = _fact_summary(fact, overrides)
    return FactOut(
        **summary.model_dump(),
        body=fact.body,
        origins=[
            OriginOut(
                agent=o.agent,
                native_path=o.native_path,
                anchor=o.anchor,
                captured_at=o.captured_at,
                source_written_at=o.source_written_at,
            )
            for o in fact.origins
        ],
    )


def _delivery_out(s: Any) -> DeliveryStatusOut:
    return DeliveryStatusOut(
        agent=s.agent,
        installed=s.installed,
        command=s.command,
        event=s.event,
    )


@router.get("/partitions", response_model=PartitionListOut)
async def list_partitions(
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> PartitionListOut:
    found = await svc.list_partitions()
    return PartitionListOut(
        partitions=[
            PartitionOut(name=p.name, project_root=p.project_root, fact_count=p.fact_count)
            for p in found
        ]
    )


@router.get("/partitions/{name}/facts", response_model=FactListOut)
async def list_facts(
    name: str,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    override_repo: Any = Depends(get_memory_override_repo),  # noqa: B008
) -> FactListOut:
    await _require_partition(name, resources)
    facts = await svc.list_facts(name)
    overrides = dict(await override_repo.all())
    return FactListOut(facts=[_fact_summary(f, overrides) for f in facts])


@router.get("/partitions/{name}/facts/{slug}", response_model=FactOut)
async def get_fact(
    name: str,
    slug: str,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    override_repo: Any = Depends(get_memory_override_repo),  # noqa: B008
) -> FactOut:
    await _require_partition(name, resources)
    facts = await svc.list_facts(name)
    fact = next((f for f in facts if f.slug == slug), None)
    if fact is None:
        raise FactNotFound(name, slug)
    overrides = dict(await override_repo.all())
    return _fact_out(fact, overrides)


@router.post("/sync", response_model=AggregationResultOut)
async def sync(
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> AggregationResultOut:
    result = await svc.aggregate(actor=actor)
    return AggregationResultOut(
        partitions=list(result.partitions),
        facts_written=result.facts_written,
        sources_read=result.sources_read,
        sources_skipped=result.sources_skipped,
        failures=[f.path for f in result.failures],
    )


@router.post("/partitions/{name}/organise", response_model=OrganiseResultOut)
async def organise(
    name: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> OrganiseResultOut:
    await _require_partition(name, resources)
    result = await get_organise_runner()(name)
    await audit.record(
        _EVENT_ORGANISED,
        ref=ResourceRef(KIND_MEMORY, name),
        actor=actor,
        details={
            "merged": result.merged,
            "superseded": result.superseded,
            "conflicts": result.conflicts,
            "model_used": result.model_used,
        },
    )
    return OrganiseResultOut(
        partition=result.partition,
        merged=result.merged,
        superseded=result.superseded,
        conflicts=result.conflicts,
        model_used=result.model_used,
    )


@router.post("/context", response_model=ComposedContextOut)
async def context(
    body: ContextQuery,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    override_repo: Any = Depends(get_memory_override_repo),  # noqa: B008
    delivery: Any = Depends(get_memory_delivery_service),  # noqa: B008
) -> ComposedContextOut:
    composed = await compose_context(
        svc,
        override_repo,
        agent=body.agent,
        cwd=body.cwd,
        budget_tokens=body.budget_tokens or DEFAULT_BUDGET_TOKENS,
    )
    if body.record_fired and body.agent:
        await delivery.record_fired(body.agent)
    return ComposedContextOut(
        text=composed.text,
        partition=composed.partition,
        facts_included=composed.facts_included,
        facts_omitted=composed.facts_omitted,
        layers=list(composed.layers),
    )


@router.get("/overrides", response_model=OverrideListOut)
async def list_overrides(
    override_repo: Any = Depends(get_memory_override_repo),  # noqa: B008
) -> OverrideListOut:
    all_overrides = await override_repo.all()
    return OverrideListOut(overrides=[_override_out(o) for o in all_overrides.values()])


@router.get("/facts/{fact_key}/override", response_model=OverrideOut)
async def get_override(
    fact_key: str,
    override_repo: Any = Depends(get_memory_override_repo),  # noqa: B008
) -> OverrideOut:
    found = await override_repo.get(fact_key)
    return _override_out(found or Override(fact_key=fact_key))


@router.patch("/facts/{fact_key}/override", response_model=OverrideOut)
async def patch_override(
    fact_key: str,
    body: OverridePatch,
    override_repo: Any = Depends(get_memory_override_repo),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> OverrideOut:
    current = await override_repo.get(fact_key) or Override(fact_key=fact_key)
    # Only fields the caller actually named are applied (a bare `null` is
    # treated the same as omitting the field); clearing one deliberately goes
    # through DELETE instead, so a PATCH can never accidentally reset a
    # decision the caller did not mean to touch.
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    updated = replace(current, **changes)
    await override_repo.set(updated, actor=actor)
    await audit.record(_EVENT_OVERRIDE_SET, actor=actor, details={"fact_key": fact_key, **changes})
    return _override_out(updated)


@router.delete("/facts/{fact_key}/override", response_model=OverrideOut)
async def clear_override_field(
    fact_key: str,
    field: str = Query(..., pattern="^(hidden|pinned|superseded_by|conflict_choice)$"),
    override_repo: Any = Depends(get_memory_override_repo),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> OverrideOut:
    current = await override_repo.get(fact_key)
    if current is None:
        return _override_out(Override(fact_key=fact_key))
    default: bool | str = False if field in ("hidden", "pinned") else ""
    updated = replace(current, **{field: default})
    if updated == Override(fact_key=fact_key):
        await override_repo.clear(fact_key)
    else:
        await override_repo.set(updated, actor=actor)
    await audit.record(
        _EVENT_OVERRIDE_CLEARED, actor=actor, details={"fact_key": fact_key, "field": field}
    )
    return _override_out(updated)


@router.get("/delivery", response_model=DeliveryStatusListOut)
async def delivery_status(
    agent: str | None = Query(default=None),
    svc: Any = Depends(get_memory_delivery_service),  # noqa: B008
) -> DeliveryStatusListOut:
    statuses = await svc.status(agent)
    return DeliveryStatusListOut(delivery=[_delivery_out(s) for s in statuses])


@router.post("/delivery/{agent}/install", response_model=DeliveryStatusOut)
async def install_delivery(
    agent: str,
    svc: Any = Depends(get_memory_delivery_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> DeliveryStatusOut:
    return _delivery_out(await svc.install(agent, actor=actor))


@router.delete("/delivery/{agent}", response_model=DeliveryStatusOut)
async def remove_delivery(
    agent: str,
    svc: Any = Depends(get_memory_delivery_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> DeliveryStatusOut:
    return _delivery_out(await svc.remove(agent, actor=actor))
