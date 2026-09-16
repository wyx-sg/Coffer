"""Internal-engine default path for ``ProviderService`` (spec provider-switching).

Two things happen when the internal engine's connection changes, and the second
is why this is its own module rather than three lines inside the service.

The flag: at most one connection globally carries ``internal_default`` (FR-021),
so the target is set only after the flag is cleared everywhere else — sequential
clear-then-set, serialised by the single-process daemon.

The model: the internal engine's model is a global singleton (E3) with no link
to the connection, so switching the connection used to leave the previous
connection's model standing — the user saw provider "Agnes" paired with
``deepseek-flash`` — and Coffer's own background passes then ran against a model
the endpoint has never heard of. A move therefore forgets the model, unless the
newly-chosen connection CURATES it: a curated list is that connection's own
catalogue, so an id on it is still servable. Nothing is probed to decide —
a settings write must not depend on an endpoint being reachable.

The model singleton belongs to another kind, so both directions (read it, forget
it) arrive as ports the composition root satisfies rather than as an imported
service. Either being absent means the test-convenience construction: there is
nothing to read and nothing to clear, so the model is left alone.
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
        await _drop_model_unless_curated(service, resource, actor=actor)
    await service._audit.record(
        AuditEventType.PROVIDER_INTERNAL_DEFAULT_SET.value,
        ref=service._ref(name),
        actor=actor,
        details={"from": previous, "to": name},
    )
    return await service.get(name)


async def _drop_model_unless_curated(
    service: ProviderService, resource: Resource, *, actor: str
) -> None:
    """Forget the internal-engine model unless ``resource`` curates it.

    Cleared, ``resolve_internal_connection()`` returns ``None`` — already the
    documented clean no-op (FR-023) — and the operator picks a model from the
    connection now in force.
    """
    if service._resolve_internal_model is None or service._clear_internal_model is None:
        return
    model = await service._resolve_internal_model()
    if not model:
        return
    if model in {m.id for m in service._cfg(resource).models}:
        return
    await service._clear_internal_model(actor)
