"""Ports the application reaches Coffer's internal engine through.

Three consumers need the same two things: the connection Coffer's internal
engine runs on, and a one-shot completion. Knowledge's tidy and ingestion and
memory's organise pass all reach for them, so they live above every kind rather
than inside one — filing them under `knowledge` was only ever true while
knowledge was the sole consumer, and it made `application.memory` import
`application.knowledge` to get at them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    # Annotation-only: the port names the provider kind's connection value
    # object without executing any of the provider kind's code.
    from coffer.domain.provider.config import ResolvedConnection


class ModelSelectorPort(Protocol):
    """Resolves Coffer's internal-engine connection (the internal-default one)."""

    async def get_default(self) -> ResolvedConnection | None: ...


class LlmCompletionPort(Protocol):
    """One shot of a model, for the small jobs that are not an agentic loop.

    Ingestion uses it to write a document's one-line ``description``, which the
    catalogue then lives or dies by. Like every other use of the internal
    connection in this layer it is optional: with none configured the caller
    falls back to the document's own opening prose (spec knowledge FR-023).
    """

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: ResolvedConnection,
        credential_resolver: Callable[[str], str],
    ) -> str: ...
