"""What becomes of the engine's model when the engine's connection moves.

The internal engine's model is a global singleton (spec internal-engine) with
no link to the connection, so switching the connection used to leave the
previous connection's model standing — the user saw provider "Agnes" paired
with ``deepseek-flash`` — and Coffer's own background passes then ran against a
model the endpoint has never heard of. A move therefore forgets the model,
unless the newly-chosen connection CURATES it: a curated list is that
connection's own catalogue, so an id on it is still servable. Nothing is
probed to decide — a settings write must not depend on an endpoint being
reachable.

Cleared, ``engine.resolve.resolve_internal_connection`` answers ``None`` —
already the documented clean no-op — and the operator picks a model from the
connection now in force.

The rule is the ENGINE's: it is the engine's model, and the engine's own idea
of when a model has stopped being servable. What the provider kind contributes
is the trigger and the curated ids; it calls this through a protocol IT
declares, so neither package imports the other.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Protocol


class InternalEngineModelStore(Protocol):
    """The engine's model singleton, narrowed to what this needs of it: read a
    model, and forget it.

    Two models live on that row — the one Coffer thinks with and the one it
    transcribes speech with — because they are chosen the same way and moved
    for the same reason, on two different connections.
    """

    async def get_model(self) -> str | None: ...

    async def clear_model(self, *, actor: str) -> None: ...

    async def get_transcribe_model(self) -> str | None: ...

    async def clear_transcribe_model(self, *, actor: str) -> None: ...


class InternalDefaultModelGuard:
    """Told when the engine's connection moves; decides the model's fate.

    Satisfies the provider kind's own ``EngineNotifyPort`` structurally — that
    kind declares the protocol it calls, so it imports nothing of the engine's
    and the kind-agnostic contract holds in both directions.
    """

    def __init__(self, models: InternalEngineModelStore) -> None:
        self._models = models

    async def drop_model_unless_curated(self, curated_ids: Collection[str], *, actor: str) -> None:
        """Forget the internal-engine model unless the connection now in force
        curates it. ``curated_ids`` are that connection's own catalogue."""
        model = await self._models.get_model()
        if not model:
            return
        if model in curated_ids:
            return
        await self._models.clear_model(actor=actor)

    async def drop_transcribe_model_unless_curated(
        self, curated_ids: Collection[str], *, actor: str
    ) -> None:
        """The same rule for the speech-to-text model when ITS connection moves.

        Same reasoning, different row: a transcription model is even less
        portable between endpoints than a chat model — most gateways serve no
        transcription endpoint at all — so a model left standing across a move
        is a 404 on the next voice message rather than a clean no-op.
        """
        model = await self._models.get_transcribe_model()
        if not model:
            return
        if model in curated_ids:
            return
        await self._models.clear_transcribe_model(actor=actor)


__all__ = ["InternalDefaultModelGuard", "InternalEngineModelStore"]
