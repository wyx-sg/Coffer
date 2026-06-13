"""Ports for the transcript-distillation slice.

Implemented in infrastructure, wired at composition root.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from coffer.domain.chat.model import ModelConfig
from coffer.domain.distill.session import DistilledInsight, TranscriptSession


class TranscriptReaderPort(Protocol):
    def list_sessions(
        self, *, agent_type_value: str, config_dir: str
    ) -> list[TranscriptSession]: ...

    def read_session(
        self, *, agent_type_value: str, config_dir: str, session_id: str
    ) -> TranscriptSession: ...


class LlmCompletionPort(Protocol):
    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: ModelConfig,
        credential_resolver: Callable[[str], str],
    ) -> str: ...


class InsightSinkPort(Protocol):
    async def record(
        self,
        *,
        project_path: str | None,
        insight: DistilledInsight,
        origin_session_id: str,
    ) -> str: ...  # returns created fact id


class AgentResolverPort(Protocol):
    async def resolve(self, name: str) -> tuple[str, str]: ...  # (agent_type_value, config_dir)


class ModelSelectorPort(Protocol):
    async def get_default(self) -> ModelConfig | None: ...

    async def get(self, model_id: str) -> ModelConfig | None: ...
