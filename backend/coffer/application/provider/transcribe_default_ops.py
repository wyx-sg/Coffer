"""Speech-to-text default path for ``ProviderService`` (spec internal-engine).

The twin of :mod:`coffer.application.provider.internal_default_ops`, kept
beside it rather than folded into it. The two flags have the same shape — at
most one connection globally, cleared everywhere else before the target is set,
the move audited — and the same consequence when the connection moves: a model
chosen for the old endpoint is not a model the new one has heard of.

They are NOT the same flag, and nothing here falls back to the other one. A
gateway that serves chat completions commonly serves no transcription endpoint
at all, so a fallback would aim every voice message at a 404 in place of the
behaviour the chat surface already has for an unconfigured vault: hand the
agent the audio file and leave the recording on this machine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.provider.config import ResolvedConnection
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


async def transcribe_connection(service: ProviderService, model: str) -> ResolvedConnection | None:
    """The connection carrying the flag, paired with ``model``.

    The provider kind answers only WHICH connection carries it and mints the
    pairing — ``ResolvedConnection`` is this kind's own value object. Whether
    there is a model to pair at all is the engine's rule, in
    ``application.engine.resolve``.
    """
    for r in await service.list():
        rc = service._cfg(r)
        if rc.transcribe_default:
            return ResolvedConnection(config=rc, model=model)
    return None


async def _set_flag(
    service: ProviderService, resource: Resource, *, value: bool, actor: str
) -> None:
    config = dict(resource.config)
    config["transcribe_default"] = value
    await service._resources.update_config(resource.uid, config, actor)


async def set_transcribe_default(service: ProviderService, uid: str, *, actor: str) -> Resource:
    """Make this connection the global speech-to-text connection."""
    resource = await service.get(uid)
    previous: str | None = None
    for r in await service.list():
        # Identity, not label: "is this the row being marked" must not be
        # decided by a string the user may change between two reads.
        if r.uid == uid:
            continue
        if service._cfg(r).transcribe_default:
            await _set_flag(service, r, value=False, actor=actor)
            previous = r.name
    if not service._cfg(resource).transcribe_default:
        # Only a real move rewrites the model, exactly as the internal-engine
        # flag does: re-marking the connection that already carries it changes
        # nothing, and dropping the model there would be a surprise.
        await _set_flag(service, resource, value=True, actor=actor)
        if service._engine is not None:
            await service._engine.drop_transcribe_model_unless_curated(
                {m.id for m in service._cfg(resource).models}, actor=actor
            )
    await service._audit.record(
        AuditEventType.PROVIDER_TRANSCRIBE_DEFAULT_SET.value,
        resource=resource,
        actor=actor,
        # Labels for the reader; the row the event belongs to travels as
        # ``resource``, so the trail survives a rename of either connection.
        details={"from": previous, "to": resource.name},
    )
    return await service.get(uid)
