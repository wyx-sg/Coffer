"""Global internal-engine model service (spec internal-engine "Resolve the engine's
connection and model together").

Coffer's internal LLM engine (aggregation / distil / knowledge curation)
takes its endpoint + key from the ``internal_default`` connection but its MODEL
from this singleton — the connection no longer owns a model. The wiring overlays
``get().model`` onto the resolved connection before building the chat model."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.application.engine_timeout import MAX_MODEL_TIMEOUT_S, MIN_MODEL_TIMEOUT_S
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigValidationError
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
    async def set_model_timeout(self, seconds: int | None) -> GlobalInternalEngineConfig: ...
    async def set_transcribe_model(self, model: str | None) -> GlobalInternalEngineConfig: ...
    async def set_curation_owner(self, machine_id: str | None) -> GlobalInternalEngineConfig: ...


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

    async def set_model_timeout(
        self, seconds: int | None, *, actor: str = "api"
    ) -> GlobalInternalEngineConfig:
        """Bound every call to Coffer's own model, or return to the default.

        Out of range is refused here rather than clamped: this is the operator
        asking for a number, and a request silently turned into a different
        number is worse than a rejection they can read. The background passes
        clamp instead — see ``engine_timeout.resolve_timeout`` for why the two
        differ.
        """
        if seconds is not None and not (MIN_MODEL_TIMEOUT_S <= seconds <= MAX_MODEL_TIMEOUT_S):
            raise ConfigValidationError(
                f"model timeout must be between {MIN_MODEL_TIMEOUT_S} and "
                f"{MAX_MODEL_TIMEOUT_S} seconds (got {seconds})"
            )
        saved = await self._repo.set_model_timeout(seconds)
        await self._audit.record(
            AuditEventType.INTERNAL_ENGINE_MODEL_SET.value,
            actor=actor,
            details={"model_timeout_s": saved.model_timeout_s},
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

    async def set_curation_owner(
        self, machine_id: str | None, *, actor: str = "api"
    ) -> GlobalInternalEngineConfig:
        """Name the one machine that may run the curation pass; ``None`` clears.

        The counterpart of binding a channel, and it exists for the same
        reason: the owner travels with this document, so a retired machine
        leaves an owner nobody claims, the pass stops on every machine, and
        without this there was no way to take it back (spec vault-sync
        "Report and change the rewriter's owner").

        The id is not checked against the machine registry. Reading the
        registry means reading the sync working tree, and a vault that has
        never converged has no registry at all — the one install where
        validating would refuse the only correct answer, its own machine.
        """
        cleaned = machine_id.strip() if machine_id and machine_id.strip() else None
        saved = await self._repo.set_curation_owner(cleaned)
        await self._audit.record(
            AuditEventType.INTERNAL_ENGINE_MODEL_SET.value,
            actor=actor,
            details={"curate_owner_machine_id": saved.curate_owner_machine_id},
        )
        return saved

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
                "auto_distil_enabled": saved.auto_distil_enabled,
                "distil_interval_s": saved.distil_interval_s,
                "curate_interval_s": saved.curate_interval_s,
            },
        )
        return saved
