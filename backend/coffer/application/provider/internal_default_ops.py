"""Internal-engine default path for ``ProviderService`` (spec provider-switching).

Two things happen when the internal engine's connection changes, and the second
is why this is its own module rather than three lines inside the service.

The flag (FR-024/FR-025, this kind's own): at most one connection globally
carries ``internal_default``, so the target is set only after the flag is
cleared everywhere else — sequential clear-then-set, serialised by the
single-process daemon — and the move is audited.

The model (spec internal-engine FR-005, NOT this kind's): the internal engine's
model is a global singleton with no link to the connection, and a move that
left the old model standing aimed Coffer's own passes at a model the new
endpoint has never heard of. What to do about that is the engine's rule and
lives in ``application.engine.internal_default``; this module supplies the
trigger and the new connection's curated ids, through a port declared on this
side (``ports.EngineNotifyPort``) so neither package imports the other.
``None`` there is the test-convenience construction: no engine to tell, so the
model is left alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


async def set_internal_default(service: ProviderService, name: str, *, actor: str) -> Resource:
    """Make ``name`` the global internal-engine default."""
    resource = await service.get(name)
    previous: str | None = None
    for r in await service.list():
        if r.name == name:
            continue
        if service._cfg(r).internal_default:
            await service._set_internal_default_flag(r, value=False, actor=actor)
            previous = r.name
    if not service._cfg(resource).internal_default:
        # Only a real move rewrites the model; re-setting the connection that is
        # already the internal default changes nothing.
        await service._set_internal_default_flag(resource, value=True, actor=actor)
        if service._engine is not None:
            # The connection now in force publishes its own catalogue; the
            # engine decides from it whether the model it holds still stands.
            await service._engine.drop_model_unless_curated(
                {m.id for m in service._cfg(resource).models}, actor=actor
            )
    await service._audit.record(
        AuditEventType.PROVIDER_INTERNAL_DEFAULT_SET.value,
        ref=service._ref(name),
        actor=actor,
        details={"from": previous, "to": name},
    )
    return await service.get(name)
