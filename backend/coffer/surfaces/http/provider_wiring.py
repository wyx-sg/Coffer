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
from coffer.application.provider.boot_reconcile import ProviderProjectionBootHeal
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.projector import ProviderProjector
from coffer.application.provider.service import ProviderService
from coffer.application.provider.sync_reconcile import ProviderProjectionReconcile
from coffer.application.resource_service import ResourceService
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.surfaces.http.dependencies import get_internal_engine_config_service
from coffer.surfaces.http.provider_dependencies import set_provider_service
from coffer.surfaces.http.sync_contributions import SyncContributions

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderWiring:
    """What the provider kind hands back: its service (later kinds resolve the
    internal connection through it) and the boot heal the lifespan runs."""

    service: ProviderService
    boot_heal: ProviderProjectionBootHeal


class _BootHeal(Protocol):
    """The one call ``run_provider_projection_sweep`` makes — structural, so a
    test can hand in a fake without building a ``ProviderService``."""

    async def heal(self) -> list[str]: ...


async def _resolve_internal_model() -> str | None:
    """The internal-engine model (spec provider-switching amendment), resolved
    lazily PER CALL: this runs at request time, long after wiring, so the
    config service is read through its getter rather than captured here."""
    return (await get_internal_engine_config_service().get()).model


async def _clear_internal_model(actor: str) -> None:
    """Forget the internal-engine model — what the provider service calls when
    the internal default moves to a connection that does not curate the model
    in force (spec provider-switching E3). Resolved lazily per call for the
    same reason as the getter above, and audited like any other write of the
    singleton."""
    await get_internal_engine_config_service().update(model=None, actor=actor)


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
        resolve_internal_model=_resolve_internal_model,
        clear_internal_model=_clear_internal_model,
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
    return ProviderWiring(service=provider_svc, boot_heal=boot_heal)


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
