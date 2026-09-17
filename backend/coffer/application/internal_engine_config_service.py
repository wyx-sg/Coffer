"""Global internal-engine model service (spec provider-switching amendment 2026-06-22b).

Coffer's internal LLM engine (aggregation / organise / knowledge curation)
takes its endpoint + key from the ``internal_default`` connection but its MODEL
from this singleton — the connection no longer owns a model. The wiring overlays
``get().model`` onto the resolved connection before building the chat model."""

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
        self,
        *,
        model: str | None,
        curate_owner_machine_id: str | None = None,
        upkeep: Mapping[str, UpkeepSetting] | None = None,
    ) -> GlobalInternalEngineConfig: ...


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

    async def set_upkeep(
        self, pass_name: str, setting: UpkeepSetting, *, actor: str = "api"
    ) -> GlobalInternalEngineConfig:
        """Change one unattended pass's switch or timer, leaving the rest.

        A settings page toggles one row at a time, and an update that carried
        the whole config would make every such toggle a chance to write back a
        stale copy of the other two — the classic lost update, on settings the
        operator may also be changing on another machine (they converge through
        vault sync).

        Curation is one of these passes: its switch is the
        ``auto_curate_enabled`` column, which the repo writes from this map
        like any other pass's, so there is one path to it.
        """
        current = await self.get()
        return await self.update(
            model=current.model,
            curate_owner_machine_id=None,
            upkeep={pass_name: setting},
            actor=actor,
        )

    async def update(
        self,
        *,
        model: str | None,
        curate_owner_machine_id: str | None = None,
        upkeep: Mapping[str, UpkeepSetting] | None = None,
        actor: str = "api",
    ) -> GlobalInternalEngineConfig:
        cleaned = model.strip() if model and model.strip() else None
        saved = await self._repo.set(
            model=cleaned,
            curate_owner_machine_id=curate_owner_machine_id,
            upkeep=upkeep,
        )
        await self._audit.record(
            AuditEventType.INTERNAL_ENGINE_MODEL_SET.value,
            actor=actor,
            details={
                "model": cleaned,
                "auto_curate_enabled": saved.auto_curate_enabled,
                "curate_owner_machine_id": saved.curate_owner_machine_id,
                "auto_aggregate_enabled": saved.auto_aggregate_enabled,
                "aggregate_interval_s": saved.aggregate_interval_s,
                "auto_organise_enabled": saved.auto_organise_enabled,
                "organise_interval_s": saved.organise_interval_s,
                "curate_interval_s": saved.curate_interval_s,
            },
        )
        return saved
