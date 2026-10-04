"""Coffer's settings service and its readers, built for the app lifespan.

The settings are one vault document (``state/settings/internal-engine.json``),
so they travel with the vault. The readers go through the DI getter rather than
a captured instance: they run at request time, long after wiring, and a value
chosen or forgotten since must take effect at once.

Split out of :mod:`coffer.surfaces.http.app` for the file-size budget.
"""

from __future__ import annotations

from coffer.application.audit_service import AuditService
from coffer.application.engine.internal_default import InternalDefaultModelGuard
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.infrastructure.persistence.internal_engine_repo import VaultInternalEngineConfigRepo
from coffer.surfaces.http.dependencies import get_internal_engine_config_service


def build_config_services(audit: AuditService) -> InternalEngineConfigService:
    """Build the internal-engine config service over its vault document."""
    return InternalEngineConfigService(repo=VaultInternalEngineConfigRepo(), audit=audit)


async def read_transcribe_model() -> str | None:
    """The speech-to-text model, or ``None`` when Coffer transcribes nothing.

    Transcription has its own connection: the endpoints that serve chat
    commonly do not serve transcription (spec internal-engine "Transcribe
    speech on its own connection and model").
    """
    return (await get_internal_engine_config_service().get()).transcribe_model


class _EngineModelStore:
    """``engine.internal_default.InternalEngineModelStore`` over the singleton.

    Clearing is audited like any other write of the singleton.
    """

    async def get_transcribe_model(self) -> str | None:
        return await read_transcribe_model()

    async def clear_transcribe_model(self, *, actor: str) -> None:
        await get_internal_engine_config_service().set_transcribe_model(None, actor=actor)


def internal_default_model_guard() -> InternalDefaultModelGuard:
    """What the provider kind notifies when the transcription connection moves."""
    return InternalDefaultModelGuard(_EngineModelStore())
