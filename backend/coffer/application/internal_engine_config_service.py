"""Coffer's own settings service (spec internal-engine "Carry a switch and interval for
each of the two unattended passes").

One singleton holds the aggregate and distil switches and timers and the
speech-to-text model."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.internal_engine_config import (
    GlobalInternalEngineConfig,
    UpkeepSetting,
)


class InternalEngineConfigRepo(Protocol):
    async def get(self) -> GlobalInternalEngineConfig | None: ...
    async def set(
        self, *, upkeep: Mapping[str, UpkeepSetting] | None = None
    ) -> GlobalInternalEngineConfig: ...
    async def set_transcribe_model(self, model: str | None) -> GlobalInternalEngineConfig: ...


class InternalEngineConfigService:
    """Reads/writes the singleton settings document."""

    def __init__(self, repo: InternalEngineConfigRepo, audit: AuditService) -> None:
        self._repo = repo
        self._audit = audit

    async def get(self) -> GlobalInternalEngineConfig:
        """The current settings, or the defaults."""
        return await self._repo.get() or GlobalInternalEngineConfig(updated_at=datetime.now(tz=UTC))

    async def set_upkeep(
        self, pass_name: str, setting: UpkeepSetting, *, actor: str = "api"
    ) -> GlobalInternalEngineConfig:
        """Change one unattended pass's switch or timer, leaving the rest.

        A settings page toggles one row at a time, and an update that carried
        the whole config would make every such toggle a chance to write back a
        stale copy of the other — the classic lost update, on settings the
        operator may also be changing on another machine (they converge through
        vault sync).
        """
        saved = await self._repo.set(upkeep={pass_name: setting})
        await self._audit.record(
            AuditEventType.INTERNAL_ENGINE_MODEL_SET.value,
            actor=actor,
            details={
                "auto_aggregate_enabled": saved.auto_aggregate_enabled,
                "aggregate_interval_s": saved.aggregate_interval_s,
                "auto_distil_enabled": saved.auto_distil_enabled,
                "distil_interval_s": saved.distil_interval_s,
            },
        )
        return saved

    async def set_transcribe_model(
        self, model: str | None, *, actor: str = "api"
    ) -> GlobalInternalEngineConfig:
        """Choose the speech-to-text model; ``None``/empty stops transcription.

        Stopping is a real answer, not a failure: with no model — or no
        connection marked ``transcribe_default`` — a turn carrying audio hands
        the agent the file untouched and the recording never leaves the
        machine.
        """
        cleaned = model.strip() if model and model.strip() else None
        saved = await self._repo.set_transcribe_model(cleaned)
        await self._audit.record(
            AuditEventType.INTERNAL_ENGINE_MODEL_SET.value,
            actor=actor,
            details={"transcribe_model": saved.transcribe_model},
        )
        return saved
