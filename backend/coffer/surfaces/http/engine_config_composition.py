"""The internal-engine config singleton, built for the app lifespan.

The engine's own settings: which model Coffer runs on its own behalf, and
whether it may tidy unattended. Building the service also registers its synced
state area, so the settings travel with the vault.

Split out of :mod:`coffer.surfaces.http.app` for the file-size budget.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.audit_service import AuditService
from coffer.application.engine_settings_sync import EngineSettingsSyncState
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.infrastructure.persistence.repos import SqlAlchemyInternalEngineConfigRepo
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
