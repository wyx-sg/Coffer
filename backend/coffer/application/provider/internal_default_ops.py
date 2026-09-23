"""Internal-engine default path for ``ProviderService`` (spec provider-switching).

Two things happen when the internal engine's connection changes, and the second
is why this is its own module rather than three lines inside the service.

The flag ("Keep at most one internal-engine default" and "Set the internal-engine
default", this kind's own): at most one connection globally
carries ``internal_default``, so the target is set only after the flag is
cleared everywhere else — sequential clear-then-set, serialised by the
single-process daemon — and the move is audited.

The model (spec internal-engine "Drop the engine model when its connection moves", NOT
this kind's): the internal engine's model is a global singleton with no link to the
connection, and a move that left the old model standing aimed Coffer's own passes at a
model the new endpoint has never heard of. What to do about that is the engine's rule
and lives in ``application.engine.internal_default``; this module supplies the trigger
and the new connection's curated ids, through a port declared on this side
(``ports.EngineNotifyPort``) so neither package imports the other. ``None`` there is the
test-convenience construction: no engine to tell, so the model is left alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.provider.config import ResolvedConnection
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


async def internal_default_connection(
    service: ProviderService, model: str
) -> ResolvedConnection | None:
    """The connection carrying the flag, paired with ``model``.

    This kind answers only WHICH connection carries it and mints the pairing —
    ``ResolvedConnection`` is its own value object. Whether there is a model to
    pair at all, and what a missing half means, are the internal engine's rule
    and live in ``application.engine``.
    """
    for r in await service.list():
        rc = service._cfg(r)
        if rc.internal_default:
            return ResolvedConnection(config=rc, model=model)
    return None


async def _set_flag(
    service: ProviderService, resource: Resource, *, value: bool, actor: str
) -> None:
    config = dict(resource.config)
    config["internal_default"] = value
    await service._resources.update_config(resource.uid, config, actor)


async def set_internal_default(service: ProviderService, uid: str, *, actor: str) -> Resource:
    """Make this connection the global internal-engine default."""
    resource = await service.get(uid)
    previous: str | None = None
    for r in await service.list():
        # Identity, not label: "is this the row being marked" must not be
        # decided by a string the user may change between two reads.
        if r.uid == uid:
            continue
        if service._cfg(r).internal_default:
            await _set_flag(service, r, value=False, actor=actor)
            previous = r.name
    if not service._cfg(resource).internal_default:
        # Only a real move rewrites the model; re-setting the connection that is
        # already the internal default changes nothing.
        await _set_flag(service, resource, value=True, actor=actor)
        if service._engine is not None:
            # The connection now in force publishes its own catalogue; the
            # engine decides from it whether the model it holds still stands.
            await service._engine.drop_model_unless_curated(
                {m.id for m in service._cfg(resource).models}, actor=actor
            )
    await service._audit.record(
        AuditEventType.PROVIDER_INTERNAL_DEFAULT_SET.value,
        resource=resource,
        actor=actor,
        # Labels for the reader; the row the event belongs to travels as
        # ``resource``, so the trail survives a rename of either connection.
        details={"from": previous, "to": resource.name},
    )
    return await service.get(uid)
