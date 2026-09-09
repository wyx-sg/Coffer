"""Memory-local ports for the agentic reorg service (spec 007).

Keeps ``application.memory`` decoupled from ``infrastructure.chat``
(Contract 2b / Contract 5e): the reorg service reaches the langgraph loop ONLY
through these injected protocols, constructed at the surfaces composition root.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from coffer.domain.provider.config import ResolvedConnection


@dataclass(frozen=True)
class ReorgTool:
    """A single internal tool the reorg agent may call."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class AgenticReorgPort(Protocol):
    """The langgraph reorg loop, seen as a memory-local protocol."""

    async def run(
        self,
        *,
        model: ResolvedConnection,
        tools: Sequence[ReorgTool],
        system_prompt: str,
        credential_resolver: Callable[[str], str],
        recursion_limit: int,
    ) -> dict[str, Any]: ...


class ModelSelectorPort(Protocol):
    """Resolves Coffer's internal-engine connection (the internal-default one)."""

    async def get_default(self) -> ResolvedConnection | None: ...
