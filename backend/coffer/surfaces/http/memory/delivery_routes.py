"""``/api/v1/memory/context`` and ``/api/v1/memory/delivery`` — the push half.

One route composes the session-start payload, three manage whether an agent's
own settings file carries the hook that asks for it. They live together because
they share a subject that the rest of the family does not have: an **agent**.

**The agent is named by uid, everywhere on this module.** The installed hook is
a string Coffer writes into somebody else's settings file once and never
revisits, so a label baked into it would start naming an agent nothing answers
to the first time the user edited it — and every session's fire would go
unattributed. There is no name fallback anywhere here (ADR
resource-identity-is-an-immutable-uid).

**Nothing here is filtered by who is asking.** A partition carries no per-agent
reach ("Serve every enabled partition to every agent"): every enabled
partition is served to every agent, so ``POST
/context`` composes the same payload whoever fired it. The agent uid identifies
the caller for the audit log and decides nothing about the content.

**No route here records an audit event of its own.** Install and remove record
theirs inside ``DeliveryService``, with the actor that asked; a second record
written at this boundary would put two rows in the log for one act.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from coffer.application.memory.context import DEFAULT_CEILING_TOKENS, compose_context
from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.service import MemoryService
from coffer.domain.memory.delivery import DeliveryStatus
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.memory.dependencies import (
    get_memory_delivery_service,
    get_memory_service,
)
from coffer.surfaces.http.memory.schemas import (
    ComposedContextOut,
    ContextQuery,
    DeliveryStatusListOut,
    DeliveryStatusOut,
)

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)


def _delivery_out(status: DeliveryStatus) -> DeliveryStatusOut:
    return DeliveryStatusOut(
        # Both halves travel, as the domain value carries them: the uid is what
        # the install and remove routes take, and the name is what the row is
        # headed with. A surface holding one would have to fetch the agent list
        # to get the other, which is the second lookup this shape removes (the
        # same reason an audit row carries ``resource_name`` beside its id).
        agent_uid=status.agent_uid,
        agent_name=status.agent_name,
        installed=status.installed,
        command=status.command,
        event=status.event,
    )


@router.post("/context", response_model=ComposedContextOut)
async def context(
    body: ContextQuery,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    delivery: DeliveryService = Depends(get_memory_delivery_service),  # noqa: B008
) -> ComposedContextOut:
    """Compose the session-start payload for one directory.

    The one route a real agent's own session reaches. ``body.agent_uid`` names
    who fired and nothing more: it does not reach ``compose_context``, which has
    no caller identity to narrow by, and exists here for ``record_fired`` — the
    audited "this agent's hook fired" event. ``record_fired`` is what the
    installed hook sets; a management surface previewing the payload leaves it
    false so it never records a fire that did not happen ("Audit every
    delivery fire").
    """
    composed = await compose_context(
        svc,
        cwd=body.cwd,
        ceiling_tokens=body.ceiling_tokens or DEFAULT_CEILING_TOKENS,
    )
    if body.record_fired and body.agent_uid:
        await delivery.record_fired(body.agent_uid)
    return ComposedContextOut(
        text=composed.text,
        partition=composed.partition,
        notes_included=composed.notes_included,
        notes_omitted=composed.notes_omitted,
    )


@router.get("/delivery", response_model=DeliveryStatusListOut)
async def delivery_status(
    agent_uid: str | None = Query(default=None),
    svc: DeliveryService = Depends(get_memory_delivery_service),  # noqa: B008
) -> DeliveryStatusListOut:
    """Delivery state for one agent, or for every agent with an adapter.

    Each row carries both the agent's uid and its name, so the surface that
    renders the list can act on a row without a second request.
    """
    statuses = await svc.status(agent_uid)
    return DeliveryStatusListOut(delivery=[_delivery_out(s) for s in statuses])


@router.post("/delivery/{agent_uid}/install", response_model=DeliveryStatusOut)
async def install_delivery(
    agent_uid: str,
    svc: DeliveryService = Depends(get_memory_delivery_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> DeliveryStatusOut:
    """Write Coffer's hook into one agent's own settings file.

    The uid is not only how this route is addressed — it is what goes INTO the
    installed command, so the entry keeps naming this agent however the user
    relabels it afterwards, and a rename costs no reinstall.
    """
    return _delivery_out(await svc.install(agent_uid, actor=actor))


@router.delete("/delivery/{agent_uid}", response_model=DeliveryStatusOut)
async def remove_delivery(
    agent_uid: str,
    svc: DeliveryService = Depends(get_memory_delivery_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> DeliveryStatusOut:
    return _delivery_out(await svc.remove(agent_uid, actor=actor))
