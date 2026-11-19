"""Coffer's own settings service (spec internal-engine "Transcribe speech on
its own connection and model"): one singleton holding the speech-to-text
model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.internal_engine_config import GlobalInternalEngineConfig


class InternalEngineConfigRepo(Protocol):
    async def get(self) -> GlobalInternalEngineConfig | None: ...
    async def set_transcribe_model(self, model: str | None) -> GlobalInternalEngineConfig: ...


class InternalEngineConfigService:
    """Reads/writes the singleton settings document."""

    def __init__(self, repo: InternalEngineConfigRepo, audit: AuditService) -> None:
        self._repo = repo
        self._audit = audit

    async def get(self) -> GlobalInternalEngineConfig:
        """The current settings, or the defaults."""
        return await self._repo.get() or GlobalInternalEngineConfig(updated_at=datetime.now(tz=UTC))

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
        was = (await self.get()).transcribe_model
        saved = await self._repo.set_transcribe_model(cleaned)
        await self._audit.record(
            AuditEventType.INTERNAL_ENGINE_MODEL_SET.value,
            actor=actor,
            details={"transcribe_model": saved.transcribe_model, "transcribe_model_from": was},
        )
        return saved
