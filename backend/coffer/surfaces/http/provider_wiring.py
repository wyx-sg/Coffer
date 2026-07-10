"""Composition-root wiring for the ``provider`` kind (spec 011).

Registers the kind into ``app.state.kinds`` (so it gets CRUD + audit + sync for
free) and constructs the :class:`ProviderService`, exposed via the DI getter.
Call this AFTER ``wire_agent_and_skill_kinds`` — the service needs the agent
service to know which agents to project into.
"""

from __future__ import annotations

import platform

from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.projector import ProviderProjector
from coffer.application.provider.service import ProviderService
from coffer.application.provider.sync_reconcile import ProviderProjectionReconcile
from coffer.application.resource_service import ResourceService
from coffer.application.sync.identity import MachineIdentityService
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.knowledge.ids import new_ulid
from coffer.infrastructure.sync.persistence import SqlAlchemyMachineIdentityRepo
from coffer.surfaces.http.dependencies import (
    get_agent_service,
    get_internal_engine_config_service,
    set_provider_service,
)


async def _resolve_internal_model() -> str | None:
    """The internal-engine model (spec 011 amendment), resolved lazily so the
    config service need only be set before the first internal-engine call."""
    return (await get_internal_engine_config_service().get()).model


def wire_provider_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    credential_store: object,
    sm: object,
) -> ProviderService:
    """Wire the ``provider`` kind (spec 011) into the app."""
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

    # ADR-045 machine axis (spec 004 amendment, Task 12): this daemon's stable
    # sync identity, built exactly as agent_skill_wiring.py / channel_wiring.py
    # do, so the projection reconcile below excludes agents scoped to a
    # different machine instead of projecting into a dead directory.
    identity = MachineIdentityService(
        SqlAlchemyMachineIdentityRepo(sm),  # type: ignore[arg-type]
        audit,
        new_id=new_ulid,
        default_name=lambda: platform.node() or "coffer",
    )

    async def _local_machine_id() -> str:
        return (await identity.get()).machine_id

    # Import reconciliation (spec 010): after every sync import, re-derive the
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
            machine_id=_local_machine_id,
        )
    )
    return provider_svc
