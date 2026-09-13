"""Ports the application reaches Coffer's internal engine through.

Four consumers now need the same three things: the connection Coffer's
internal engine runs on, a one-shot completion, and an embedder. Knowledge's
tidy and ingestion, ranked retrieval, and memory's organise pass all reach for
them, so they live above every kind rather than inside one — filing them under
`knowledge` was only ever true while knowledge was the sole consumer, and it
made `application.memory` import `application.knowledge` to get at them.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from coffer.domain.provider.config import ResolvedConnection


class ModelSelectorPort(Protocol):
    """Resolves Coffer's internal-engine connection (the internal-default one)."""

    async def get_default(self) -> ResolvedConnection | None: ...


class EmbedderPort(Protocol):
    """Turns text into vectors.

    Contract, and the reason ranked retrieval can never fail a call: ``embed``
    returns one vector per input in order, or an empty tuple. It does not
    raise. An empty tuple means "ranking is unavailable right now", which the
    caller answers with a literal search rather than an error (spec knowledge
    FR-027).
    """

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


class LlmCompletionPort(Protocol):
    """One shot of a model, for the small jobs that are not an agentic loop.

    Ingestion uses it to write a document's one-line ``description``, which the
    catalogue then lives or dies by. Like every other use of the internal
    connection in this layer it is optional: with none configured the caller
    falls back to the document's own opening prose (spec knowledge FR-034).
    """

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: ResolvedConnection,
        credential_resolver: Callable[[str], str],
    ) -> str: ...
