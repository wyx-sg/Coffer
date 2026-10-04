"""What becomes of the speech-to-text model when its connection moves.

The transcription model is a global singleton (spec internal-engine) with no
link to the connection, so switching the connection would leave the previous
connection's model standing and the next voice message would aim at a model the
endpoint has never heard of. A move therefore forgets the model, unless the
newly-chosen connection CURATES it: a curated list is that connection's own
catalogue, so an id on it is still servable. Nothing is probed to decide — a
settings write must not depend on an endpoint being reachable.

The rule is the engine's: it is the engine's model, and the engine's own idea
of when a model has stopped being servable. What the provider kind contributes
is the trigger and the curated ids; it calls this through a protocol IT
declares, so neither package imports the other.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Protocol


class InternalEngineModelStore(Protocol):
    """The settings singleton, narrowed to what this needs of it: read the
    speech-to-text model, and forget it."""

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

    async def drop_transcribe_model_unless_curated(
        self, curated_ids: Collection[str], *, actor: str
    ) -> None:
        """Forget the speech-to-text model unless the connection now in force
        curates it. ``curated_ids`` are that connection's own catalogue.

        A transcription model is not portable between endpoints — most gateways
        serve no transcription endpoint at all — so a model left standing across
        a move is a 404 on the next voice message rather than a clean no-op.
        """
        model = await self._models.get_transcribe_model()
        if not model:
            return
        if model in curated_ids:
            return
        await self._models.clear_transcribe_model(actor=actor)


__all__ = ["InternalDefaultModelGuard", "InternalEngineModelStore"]
