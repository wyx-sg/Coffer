"""Composition-root wiring for the ``provider`` kind (spec provider-switching).

Registers the kind into ``app.state.kinds`` (so it gets CRUD + audit + sync for
free) and constructs the :class:`ProviderService`, exposed via the DI getter.
Call this AFTER ``wire_agent_and_skill_kinds`` — the service needs the agent
service to know which agents to project into.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.application.provider.boot_reconcile import ProviderProjectionBootHeal
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.projector import ProviderProjector
from coffer.application.provider.service import ProviderService
from coffer.application.provider.sync_reconcile import ProviderProjectionReconcile
from coffer.application.resource_service import ResourceService
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.surfaces.http.dependencies import (
    get_agent_service,
    get_internal_engine_config_service,
    set_provider_service,
)

_log = logging.getLogger(__name__)


async def _resolve_internal_model() -> str | None:
    """The internal-engine model (spec provider-switching amendment), resolved lazily so the
    config service need only be set before the first internal-engine call."""
    return (await get_internal_engine_config_service().get()).model


def wire_provider_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    credential_store: object,
    sm: object,
) -> ProviderService:
    """Wire the ``provider`` kind (spec provider-switching) into the app."""
    app.state.kinds["provider"] = make_provider_kind()
    provider_svc = ProviderService(
        resources=resource_svc,
        credentials=credential_store,  # type: ignore[arg-type]
        config_store=ConfigFileStore(),
        agents=get_agent_service(),
        audit=audit,
        resolve_internal_model=_resolve_internal_model,
    )
    set_provider_service(provider_svc)

    # Import reconciliation (spec vault-export-import): after every sync import, re-derive the
    # desired projection from the converged provider rows and apply it to the
    # agents registered on THIS machine — a switch made elsewhere takes real
    # effect here. A second stateless projector over the same store suffices.
    hooks = getattr(app.state, "sync_post_import_hooks", None)
    if hooks is None:
        hooks = []
        app.state.sync_post_import_hooks = hooks
    hooks.append(
        ProviderProjectionReconcile(
            providers=provider_svc,
            agents=get_agent_service(),
            projector=ProviderProjector(ConfigFileStore()),
        )
    )
    # Boot heal (see run_provider_projection_sweep) — a DIFFERENT direction from
    # the import hook above: it corrects Coffer's own flag, never the agent's
    # config, because a leftover flag carries no warrant to re-route an agent.
    app.state.provider_projection_heal = ProviderProjectionBootHeal(
        providers=provider_svc,
        agents=get_agent_service(),
        config_store=ConfigFileStore(),
        deactivate=provider_svc.deactivate,
    )
    return provider_svc


async def run_provider_projection_sweep(app: FastAPI) -> None:
    """Boot hook: stop trusting an ``is_active`` flag the agent's config denies.

    See ``application/provider/boot_reconcile`` for what drifts and why this
    heals in one direction only. Best-effort: whatever it finds is logged, and
    nothing here is allowed to fail boot.
    """
    heal = getattr(app.state, "provider_projection_heal", None)
    if heal is None:
        return
    try:
        notes = await heal.heal()
    except Exception:
        _log.exception("provider_projection_sweep.failed")
        return
    for note in notes:
        _log.warning("provider_projection_sweep %s", note)
