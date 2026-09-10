"""The LLM-shaped protocols the knowledge layer is allowed to know about.

Coffer's internal engine runs on langgraph/langchain, both of which live in
``infrastructure.llm``. The application layer may not import that (the layered
import contract), so every LLM capability it needs is declared here as a
Protocol and injected at the surfaces composition root. Structural typing is
what makes that work: the adapter never imports these definitions, and these
definitions never import the adapter.

Named for the tidy pass because that is the one consumer that survives, but
:class:`LlmCompletionPort` is deliberately kept alongside: a one-shot
completion is the other shape the engine is asked for, and re-deriving it at
the next call site is how two subtly different copies of one contract appear.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from coffer.domain.provider.config import ResolvedConnection


@dataclass(frozen=True)
class ReorgTool:
    """A single internal tool the tidy pass's agent may call."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class AgenticReorgPort(Protocol):
    """The langgraph tidy loop, seen as a knowledge-local protocol."""

    async def run(
        self,
        *,
        model: ResolvedConnection,
        tools: Sequence[ReorgTool],
        system_prompt: str,
        credential_resolver: Callable[[str], str],
        recursion_limit: int,
    ) -> dict[str, Any]: ...


class LlmCompletionPort(Protocol):
    """A single one-shot chat completion (system + user → assistant text)."""

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: ResolvedConnection,
        credential_resolver: Callable[[str], str],
    ) -> str: ...


class ModelSelectorPort(Protocol):
    """Resolves Coffer's internal-engine connection (the internal-default one)."""

    async def get_default(self) -> ResolvedConnection | None: ...


__all__ = [
    "AgenticReorgPort",
    "LlmCompletionPort",
    "ModelSelectorPort",
    "ReorgTool",
]
