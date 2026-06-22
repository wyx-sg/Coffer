"""Global internal-engine model service (spec 011 amendment 2026-06-22b).

Coffer's internal LLM engine (organizer / reorg / distill / ``coffer__ask``)
takes its endpoint + key from the ``internal_default`` connection but its MODEL
from this singleton — the connection no longer owns a model. The wiring overlays
``get().model`` onto the resolved connection before building the chat model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.internal_engine_config import GlobalInternalEngineConfig


class InternalEngineConfigRepo(Protocol):
    async def get(self) -> GlobalInternalEngineConfig | None: ...
    async def set(self, *, model: str | None) -> GlobalInternalEngineConfig: ...


class InternalEngineConfigService:
    """Reads/writes the singleton internal-engine model selection."""

    def __init__(self, repo: InternalEngineConfigRepo, audit: AuditService) -> None:
        self._repo = repo
        self._audit = audit

    async def get(self) -> GlobalInternalEngineConfig:
        """The current selection, or an unset default (``model=None``)."""
        return await self._repo.get() or GlobalInternalEngineConfig(
            model=None, updated_at=datetime.now(tz=UTC)
        )

    async def update(self, *, model: str | None, actor: str = "api") -> GlobalInternalEngineConfig:
        cleaned = model.strip() if model and model.strip() else None
        saved = await self._repo.set(model=cleaned)
        await self._audit.record(
            AuditEventType.INTERNAL_ENGINE_MODEL_SET.value,
            actor=actor,
            details={"model": cleaned},
        )
        return saved
