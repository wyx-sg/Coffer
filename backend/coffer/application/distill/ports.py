"""Ports for the transcript-distillation slice.

Implemented in infrastructure, wired at composition root.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from coffer.domain.distill.session import DistilledInsight, TranscriptSession
from coffer.domain.provider.config import ProviderConfig


class TranscriptReaderPort(Protocol):
    def list_sessions(
        self, *, agent_type_value: str, config_dir: str
    ) -> list[TranscriptSession]: ...

    def list_session_summaries(
        self, *, agent_type_value: str, config_dir: str, limit: int, offset: int
    ) -> tuple[int, list[TranscriptSession]]: ...

    def search_session_summaries(
        self,
        *,
        agent_type_value: str,
        config_dir: str,
        limit: int,
        offset: int,
        query: str | None = ...,
        project: str | None = ...,
        started_after: datetime | None = ...,
        started_before: datetime | None = ...,
        sort: str = ...,
        order: str = ...,
    ) -> tuple[int, list[TranscriptSession]]: ...

    def read_session(
        self, *, agent_type_value: str, config_dir: str, session_id: str
    ) -> TranscriptSession: ...


class LlmCompletionPort(Protocol):
    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: ProviderConfig,
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
    async def get_default(self) -> ProviderConfig | None: ...
