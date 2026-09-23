"""Coffer's own engine, built for the app lifespan.

The engine's settings: which model Coffer runs on its own behalf, and whether
it may tidy unattended. Building the service also registers its synced state
area, so the settings travel with the vault.

This is also where the engine's two seams onto the provider kind are tied,
because only a composition root may see both: the guard the provider kind
notifies when the engine's connection moves, and the resolver every internal
consumer asks for the connection to run on. Both read the singleton through its
getter rather than a captured instance — they run at request time, long after
wiring, and a model chosen or forgotten since must take effect at once.

Split out of :mod:`coffer.surfaces.http.app` for the file-size budget.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.audit_service import AuditService
from coffer.application.engine.internal_default import InternalDefaultModelGuard
from coffer.application.engine.resolve import (
    InternalDefaultConnectionPort,
    InternalEngineConnection,
)
from coffer.application.engine_settings_sync import EngineSettingsSyncState
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.infrastructure.persistence.repos import SqlAlchemyInternalEngineConfigRepo
from coffer.surfaces.http.dependencies import get_internal_engine_config_service
from coffer.surfaces.http.sync_contributions import SyncContributions


def build_config_services(
    sm: async_sessionmaker[AsyncSession],
    audit: AuditService,
    sync: SyncContributions,
) -> InternalEngineConfigService:
    """Build the internal-engine config service and register its synced state
    area (spec vault-sync slice 7) before ``start_sync`` snapshots."""
    internal_repo = SqlAlchemyInternalEngineConfigRepo(sm)
    internal_svc = InternalEngineConfigService(repo=internal_repo, audit=audit)
    sync.state_providers.append(EngineSettingsSyncState(internal_svc, internal_repo=internal_repo))
    return internal_svc


async def read_internal_engine_timeout() -> int | None:
    """How long one call to Coffer's own model may take, or ``None`` for the
    default. An ``engine_timeout.TimeoutReader``, read per call for the reason
    in the module docstring."""
    return (await get_internal_engine_config_service().get()).model_timeout_s


async def read_transcribe_model() -> str | None:
    """The speech-to-text model, or ``None`` when Coffer transcribes nothing.

    Deliberately NOT falling back to the engine model: they run on different
    connections and the endpoints that serve one commonly do not serve the
    other (spec internal-engine "Transcribe speech on its own connection and
    model").
    """
    return (await get_internal_engine_config_service().get()).transcribe_model


async def read_internal_engine_model() -> str | None:
    """The model Coffer's own engine runs on, or ``None`` if none is chosen.

    An ``engine.resolve.InternalModelReader``. Read through the DI getter per
    call, for the reason in the module docstring.
    """
    return (await get_internal_engine_config_service().get()).model


class _EngineModelStore:
    """``engine.internal_default.InternalEngineModelStore`` over the singleton.

    Clearing is audited like any other write of the singleton.
    """

    async def get_model(self) -> str | None:
        return await read_internal_engine_model()

    async def clear_model(self, *, actor: str) -> None:
        await get_internal_engine_config_service().update(model=None, actor=actor)

    async def get_transcribe_model(self) -> str | None:
        return await read_transcribe_model()

    async def clear_transcribe_model(self, *, actor: str) -> None:
        await get_internal_engine_config_service().set_transcribe_model(None, actor=actor)


def internal_default_model_guard() -> InternalDefaultModelGuard:
    """What the provider kind notifies when the engine's connection moves."""
    return InternalDefaultModelGuard(_EngineModelStore())


def internal_engine_connection(
    connections: InternalDefaultConnectionPort,
) -> InternalEngineConnection:
    """The connection Coffer's internal engine runs on, for every consumer of
    it: knowledge's ingest and tidy, memory's organise, vault-sync's conflict
    resolver, chat's voice transcription."""
    return InternalEngineConnection(read_model=read_internal_engine_model, connections=connections)
