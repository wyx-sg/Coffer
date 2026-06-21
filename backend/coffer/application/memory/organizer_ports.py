"""Ports for the memory consolidation organizer (the internal-LLM merge slice).

The langchain one-shot completion lives in ``infrastructure.chat`` (Contract 9);
the organizer reaches it ONLY through these memory-local Protocols, injected at a
composition root (``surfaces/http/organize_wiring.py``). This mirrors the
transcript-distillation slice (``application/distill/ports.py``) but is defined
memory-locally on purpose: Contract 5e forbids ``application.memory`` from
importing ``application.distill``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from coffer.domain.chat.model import ModelConfig


class LlmCompletionPort(Protocol):
    """A single one-shot chat completion (system + user → assistant text)."""

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: ModelConfig,
        credential_resolver: Callable[[str], str],
    ) -> str: ...


class ModelSelectorPort(Protocol):
    """Resolves Coffer's configured internal model (Settings → Models)."""

    async def get_default(self) -> ModelConfig | None: ...
