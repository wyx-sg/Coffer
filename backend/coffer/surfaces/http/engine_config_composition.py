"""The internal-engine config singleton, built for the app lifespan.

What used to stand here built two singletons — an embedding configuration and
the internal-engine model choice. The embedding one configured nothing once the
vector index was removed (ADR knowledge-is-plain-files), so only the engine's
own settings survive: which model Coffer runs on its own behalf, and whether it
may tidy unattended.

Split out of :mod:`coffer.surfaces.http.app` for the file-size budget.
"""

from __future__ import annotations

from typing import Any


def build_config_services(app: Any, sm: Any, audit: Any) -> Any:
    """Build the internal-engine config service and register its synced state
    area (spec vault-export-import slice 7) before ``start_sync`` snapshots."""
    from coffer.application.engine_settings_sync import EngineSettingsSyncState
    from coffer.application.internal_engine_config_service import InternalEngineConfigService
    from coffer.infrastructure.persistence.repos import SqlAlchemyInternalEngineConfigRepo

    internal_repo = SqlAlchemyInternalEngineConfigRepo(sm)
    internal_svc = InternalEngineConfigService(repo=internal_repo, audit=audit)
    providers = getattr(app.state, "sync_state_providers", None)
    if providers is None:
        providers = []
        app.state.sync_state_providers = providers
    providers.append(EngineSettingsSyncState(internal_svc, internal_repo=internal_repo))
    return internal_svc
