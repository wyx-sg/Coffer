"""``/api/v1/memory/context`` — the push half.

The route composes the session-start payload the installed hook asks for.
Whether an agent's own settings file carries that hook is not managed here: the
hook is one part of connecting the agent to Coffer (spec agent-registry
"Connect an agent to Coffer in one action"), on the agent's own routes.

**The agent is named by uid.** The installed hook is
a string Coffer writes into somebody else's settings file once and never
revisits, so a label baked into it would start naming an agent nothing answers
to the first time the user edited it — and every session's fire would go
unattributed. There is no name fallback anywhere here (ADR
resource-identity-is-an-immutable-uid).

**Nothing here is filtered by who is asking.** A partition carries no per-agent
reach and no enabled switch ("Serve every partition to every agent"): every
partition is served to every agent, so ``POST
/context`` composes the same payload whoever fired it. The agent uid identifies
the caller for the audit log and decides nothing about the content.

**The route records no audit event of its own** beyond the fire
``DeliveryService.record_fired`` writes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.memory.context import DEFAULT_CEILING_TOKENS, compose_context
from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.service import MemoryService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.memory.dependencies import (
    get_memory_delivery_service,
    get_memory_service,
)
from coffer.surfaces.http.memory.schemas import (
    ComposedContextOut,
    ContextQuery,
)

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
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
