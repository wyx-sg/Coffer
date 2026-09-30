"""``/api/v1/reconcile/*`` and ``/api/v1/attention`` — the read models over the
unified reconciler (ADR one-level-triggered-reconciler-compares-parameters).

- ``GET /reconcile/plan`` — a dry-run: for every target (or one), each
  difference between what Coffer wants and what is there, with the operation,
  the file, the safe before/after text and what the target's direction policy
  says. Filterable by the resource it concerns (``kind``, ``uid``). Computed on
  request and writes nothing, so the change preview and the drift view read
  the same plan a pass would carry out.
- ``POST /reconcile/apply`` — apply the named differences as a person asking
  for them (the manual trigger): an id whose policy still will not repair it
  comes back ``planned`` with its reason, never written.
- ``GET /attention`` — the cross-kind "needs you" list the Overview shows.
- ``PUT /attention/ignored/{key}`` / ``DELETE …`` — ignore an informational
  item on this machine, or stop ignoring it; audited.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from coffer.application.attention import AttentionService
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.reconcile import Trigger
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.reconcile_dependencies import get_attention_service, get_reconciler
from coffer.surfaces.http.reconcile_schemas import (
    AttentionOut,
    ReconcileApplyIn,
    ReconcileApplyOut,
    ReconcilePlanOut,
    ReconcileTargetOut,
    attention_out,
    item_out,
    pass_out,
)

router = APIRouter(
    prefix="/api/v1/reconcile", tags=["reconcile"], dependencies=[Depends(require_token)]
)
attention_router = APIRouter(
    prefix="/api/v1/attention", tags=["reconcile"], dependencies=[Depends(require_token)]
)

#: The triggers a plan may be computed for: what a periodic pass would do, or
#: what a person applying every item would get.
PlanTrigger = Literal["period", "manual"]


@router.get("/plan", response_model=ReconcilePlanOut)
async def get_plan(
    target: str | None = Query(default=None, description="One target's plan only."),
    kind: str | None = Query(default=None, description="Only items about this kind."),
    uid: str | None = Query(default=None, description="Only items about this resource."),
    trigger: PlanTrigger = Query(default="period"),  # noqa: B008
    reconciler: Reconciler = Depends(get_reconciler),  # noqa: B008
) -> ReconcilePlanOut:
    """Every difference a pass would find now, and what it would do about it."""
    if target is not None and target not in reconciler.target_names:
        raise HTTPException(status_code=404, detail=f"unknown reconcile target {target!r}")
    report = await reconciler.plan(targets=[target] if target else None, trigger=Trigger(trigger))
    failed = {f.target: f.error for f in report.failures}
    return ReconcilePlanOut(
        trigger=report.trigger.value,
        generated_at=report.finished_at,
        period_seconds=reconciler.period_seconds,
        targets=[
            ReconcileTargetOut(
                name=name,
                kinds=sorted(reconciler.target_kinds(name)),
                error=failed.get(name),
            )
            for name in report.targets
        ],
        items=[
            item_out(r, reconciler.first_seen(r.change.id))
            for r in report.results
            if (kind is None or r.change.difference.subject.kind == kind)
            and (uid is None or r.change.difference.subject.uid == uid)
        ],
        last_pass=pass_out(reconciler.last_pass),
    )


@router.post("/apply", response_model=ReconcileApplyOut)
async def apply_items(
    body: ReconcileApplyIn,
    actor: str = Depends(get_actor),
    reconciler: Reconciler = Depends(get_reconciler),  # noqa: B008
) -> ReconcileApplyOut:
    """Apply the named differences now. Each repair is audited with the
    caller as actor; one whose audit cannot be recorded is put back and
    reported ``failed``. An id that names no current difference is absent
    from the answer."""
    started = datetime.now(tz=UTC)
    report = await reconciler.apply(body.ids, actor=actor)
    return ReconcileApplyOut(
        started_at=started,
        finished_at=report.finished_at,
        items=[item_out(r, reconciler.first_seen(r.change.id)) for r in report.results],
        failures=[
            ReconcileTargetOut(
                name=f.target, kinds=sorted(reconciler.target_kinds(f.target)), error=f.error
            )
            for f in report.failures
        ],
    )


@attention_router.get("", response_model=AttentionOut)
async def get_attention(
    service: AttentionService = Depends(get_attention_service),  # noqa: B008
) -> AttentionOut:
    """What needs a person now, across every kind whose feature is on — each
    item with one action, the route its own page calls. Writes nothing."""
    return attention_out(await service.report())


@attention_router.put("/ignored/{key:path}", status_code=204)
async def ignore_attention_item(
    key: str,
    actor: str = Depends(get_actor),
    service: AttentionService = Depends(get_attention_service),  # noqa: B008
) -> Response:
    """Ignore the informational item ``key`` on this machine: it leaves
    ``items`` and the counts and is listed under ``ignored``. 409
    ``ATTENTION_NOT_IGNORABLE`` when nothing informational is listed under it."""
    await service.ignore(key, actor=actor)
    return Response(status_code=204)


@attention_router.delete("/ignored/{key:path}", status_code=204)
async def unignore_attention_item(
    key: str,
    actor: str = Depends(get_actor),
    service: AttentionService = Depends(get_attention_service),  # noqa: B008
) -> Response:
    """Stop ignoring ``key``; a key that is not ignored is a no-op."""
    await service.unignore(key, actor=actor)
    return Response(status_code=204)
