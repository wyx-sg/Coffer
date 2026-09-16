"""Composition-root wiring for the ``provider`` kind (spec provider-switching).

Registers the kind into ``app.state.kinds`` (so it gets CRUD + audit + sync for
free) and constructs the :class:`ProviderService`, exposed via the DI getter.
Call this AFTER ``wire_agent_and_skill_kinds`` — the service needs the agent
service to know which agents to project into, and the lifespan passes it in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from fastapi import FastAPI

from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.engine.resolve import InternalEngineConnection
from coffer.application.provider.boot_reconcile import ProviderProjectionBootHeal
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.projector import ProviderProjector
from coffer.application.provider.service import ProviderService
from coffer.application.provider.sync_reconcile import ProviderProjectionReconcile
from coffer.application.resource_service import ResourceService
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.surfaces.http.engine_config_composition import (
    internal_default_model_guard,
    internal_engine_connection,
)
from coffer.surfaces.http.provider_dependencies import set_provider_service
from coffer.surfaces.http.sync_contributions import SyncContributions

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderWiring:
    """What the provider kind hands back: its service, the boot heal the
    lifespan runs, and the internal-engine connection tied over it — the seam
    later kinds and the background workers resolve Coffer's own engine through,
    so none of them has to hold this kind's service to reach it."""

    service: ProviderService
    boot_heal: ProviderProjectionBootHeal
    internal_connection: InternalEngineConnection


class _BootHeal(Protocol):
    """The one call ``run_provider_projection_sweep`` makes — structural, so a
    test can hand in a fake without building a ``ProviderService``."""

    async def heal(self) -> list[str]: ...


def wire_provider_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    credential_store: EncryptedCredentialStore,
    agent_service: AgentService,
    sync: SyncContributions,
) -> ProviderWiring:
    """Wire the ``provider`` kind (spec provider-switching) into the app."""
    app.state.kinds["provider"] = make_provider_kind()
    provider_svc = ProviderService(
        resources=resource_svc,
        credentials=credential_store,
        config_store=ConfigFileStore(),
        agents=agent_service,
        audit=audit,
        # Coffer's own engine, told when the connection it runs on moves. The
        # engine decides the fate of its model; this kind only reports the move
        # and the new connection's catalogue (spec internal-engine FR-005).
        engine=internal_default_model_guard(),
    )
    set_provider_service(provider_svc)

    # Import reconciliation (spec vault-sync): after every sync import, re-derive the
    # desired projection from the converged provider rows and apply it to the
    # agents registered on THIS machine — a switch made elsewhere takes real
    # effect here. A second stateless projector over the same store suffices.
    sync.post_import_hooks.append(
        ProviderProjectionReconcile(
            providers=provider_svc,
            agents=agent_service,
            projector=ProviderProjector(ConfigFileStore()),
        )
    )
    # Boot heal (see run_provider_projection_sweep) — a DIFFERENT direction from
    # the import hook above: it corrects Coffer's own flag, never the agent's
    # config, because a leftover flag carries no warrant to re-route an agent.
    boot_heal = ProviderProjectionBootHeal(
        providers=provider_svc,
        agents=agent_service,
        config_store=ConfigFileStore(),
        deactivate=provider_svc.deactivate,
    )
    return ProviderWiring(
        service=provider_svc,
        boot_heal=boot_heal,
        # Tied here because this is where both halves exist: the engine's rule
        # (application.engine) and the kind that knows which row is flagged.
        internal_connection=internal_engine_connection(provider_svc),
    )


async def run_provider_projection_sweep(heal: _BootHeal) -> None:
    """Boot hook: stop trusting an ``is_active`` flag the agent's config denies.

    See ``application/provider/boot_reconcile`` for what drifts and why this
    heals in one direction only. Best-effort: whatever it finds is logged, and
    nothing here is allowed to fail boot.
    """
    try:
        notes = await heal.heal()
    except Exception:
        _log.exception("provider_projection_sweep.failed")
        return
    for note in notes:
        _log.warning("provider_projection_sweep %s", note)
