"""``/api/v1/memory/triggers`` — authored guards on known traps (spec memory
"Keep triggers in the vault, armed only by a person").

List every trigger (proposals included), write one (armed by the person who
writes it), arm a proposal, disarm one, delete one. Each trigger is a file in
``vault/memory-triggers/``; ``coffer memory trigger`` is the command-line half.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from coffer.application.memory.triggers import TriggerDraft, TriggerService
from coffer.domain.memory.trigger import Trigger
from coffer.infrastructure.memory import paths as memory_paths
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.memory.delivery_schemas import TriggerIn, TriggerListOut, TriggerOut
from coffer.surfaces.http.memory.dependencies import get_memory_trigger_service

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)


def trigger_out(t: Trigger) -> TriggerOut:
    return TriggerOut(
        id=t.id,
        note=t.note,
        kind=t.kind,
        command=t.command,
        unless=t.unless,
        error=t.error,
        armed=t.armed,
        armed_by=t.armed_by,
        armed_at=t.armed_at,
        proposed_by=t.proposed_by,
        created=t.created,
        body=t.body,
        path=str(memory_paths.triggers_root() / f"{t.id}.md"),
    )


@router.get("/triggers", response_model=TriggerListOut)
async def list_triggers(
    svc: TriggerService = Depends(get_memory_trigger_service),  # noqa: B008
) -> TriggerListOut:
    return TriggerListOut(triggers=[trigger_out(t) for t in svc.all()])


@router.post("/triggers", response_model=TriggerOut, status_code=201)
async def add_trigger(
    body: TriggerIn,
    svc: TriggerService = Depends(get_memory_trigger_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> TriggerOut:
    draft = TriggerDraft(
        note=body.note,
        kind=body.kind,
        command=body.command,
        unless=body.unless,
        error=body.error,
        body=body.body,
    )
    return trigger_out(await svc.add(draft, actor=actor))


@router.post("/triggers/{trigger_id}/arm", response_model=TriggerOut)
async def arm_trigger(
    trigger_id: str,
    svc: TriggerService = Depends(get_memory_trigger_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> TriggerOut:
    return trigger_out(await svc.arm(trigger_id, actor=actor))


@router.post("/triggers/{trigger_id}/disarm", response_model=TriggerOut)
async def disarm_trigger(
    trigger_id: str,
    svc: TriggerService = Depends(get_memory_trigger_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> TriggerOut:
    return trigger_out(await svc.disarm(trigger_id, actor=actor))


@router.delete("/triggers/{trigger_id}", status_code=204, response_class=Response)
async def delete_trigger(
    trigger_id: str,
    svc: TriggerService = Depends(get_memory_trigger_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    await svc.delete(trigger_id, actor=actor)
    return Response(status_code=204)
