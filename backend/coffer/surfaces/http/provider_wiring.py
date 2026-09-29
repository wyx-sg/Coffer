"""Composition-root wiring for the ``provider`` kind (spec provider-switching).

Registers the kind into ``app.state.kinds`` (so it gets CRUD + audit + sync for
free) and constructs the :class:`ProviderService`, exposed via the DI getter.
Call this AFTER ``wire_agent_and_skill_kinds`` — the service needs the agent
service to know which agents to project into, and the lifespan passes it in.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.engine.resolve import InternalEngineConnection
from coffer.application.provider.internal_default_guard import (
    ProviderInternalDefaultNormaliser,
)
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.projection_reconcile import ProviderProjectionTarget
from coffer.application.provider.projector import ProviderProjector
from coffer.application.provider.service import ProviderService
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.facets import AgentCatalog
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.surfaces.http.engine_config_composition import (
    internal_default_model_guard,
    internal_engine_connection,
)
from coffer.surfaces.http.provider_dependencies import set_provider_service
from coffer.surfaces.http.sync_contributions import SyncContributions


@dataclass(frozen=True)
class ProviderWiring:
    """What the provider kind hands back: its service, and the internal-engine
    connection tied over it — the seam later kinds and the background workers
    resolve Coffer's own engine through, so none of them has to hold this
    kind's service to reach it."""

    service: ProviderService
    internal_connection: InternalEngineConnection


def wire_provider_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    credential_store: EncryptedCredentialStore,
    agent_service: AgentService,
    sync: SyncContributions,
    agent_catalog: AgentCatalog,
    reconciler: Reconciler,
) -> ProviderWiring:
    """Wire the ``provider`` kind (spec provider-switching) into the app."""
    # Handed the resource table so a direct write cannot flag a second
    # internal-engine default (spec provider-switching "Keep at most one
    # internal-engine default").
    app.state.kinds["provider"] = make_provider_kind(resource_svc)
    provider_svc = ProviderService(
        resources=resource_svc,
        credentials=credential_store,
        config_store=ConfigFileStore(),
        agents=agent_service,
        audit=audit,
        # The agents' provider projection facets.
        agent_catalog=agent_catalog,
        # Coffer's own engine, told when the connection it runs on moves. The
        # engine decides the fate of its model; this kind only reports the move
        # and the new connection's catalogue (spec internal-engine "Drop the
        # engine model when its connection moves").
        engine=internal_default_model_guard(),
        # A switch is several writes; no reconcile pass judges it half done.
        hold=reconciler.hold,
    )
    set_provider_service(provider_svc)

    # A synced document flagging a second internal default is applied with the
    # flag cleared and reported, never left to fail every round.
    sync.import_normalisers.append(ProviderInternalDefaultNormaliser(resource_svc))
    # The projection into each agent's own config (ADR
    # one-level-triggered-reconciler-compares-parameters): judged by every key
    # Coffer owns there, on every pass — boot, period, hint, and the import
    # pass the reconciler's own post-import hook asks for.
    reconciler.register(
        ProviderProjectionTarget(
            providers=provider_svc,
            agents=agent_service,
            projector=ProviderProjector(ConfigFileStore(), agents=agent_catalog),
            store=ConfigFileStore(),
            deactivate=provider_svc.deactivate,
        )
    )
    return ProviderWiring(
        service=provider_svc,
        # Tied here because this is where both halves exist: the engine's rule
        # (application.engine) and the kind that knows which row is flagged.
        internal_connection=internal_engine_connection(provider_svc),
    )
