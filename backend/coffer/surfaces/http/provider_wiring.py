"""Composition-root wiring for the ``provider`` kind (spec provider-switching).

Registers the kind into ``app.state.kinds`` (so it gets CRUD + audit + sync for
free) and constructs the :class:`ProviderService`, exposed via the DI getter.
Call this AFTER ``wire_agent_and_skill_kinds`` — the service needs the agent
service to know which agents to project into, and the lifespan passes it in.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass

from fastapi import FastAPI

from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.engine.resolve import InternalEngineConnection
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.prices import ProviderPriceResolver
from coffer.application.provider.projection_reconcile import ProviderProjectionTarget
from coffer.application.provider.projector import ProviderProjector
from coffer.application.provider.secret_gate import provider_destination
from coffer.application.provider.service import ProviderService
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.secrets import SecretDestination
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.provider.reported_prices import shared_store as reported_price_store
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.infrastructure.usage.bundled_prices import load_bundled_prices
from coffer.infrastructure.usage.price_refresh import PriceListSource, refresh_pinned_off
from coffer.surfaces.http.engine_config_composition import (
    internal_default_model_guard,
    internal_engine_connection,
)
from coffer.surfaces.http.model_proxy_wiring import (
    ModelProxyWiring,
    proxy_root_now,
    wire_model_proxy,
)
from coffer.surfaces.http.price_list_routes import set_price_list_source
from coffer.surfaces.http.provider_dependencies import set_price_resolver, set_provider_service
from coffer.surfaces.http.secret_boundary_wiring import (
    get_secret_boundary,
    on_approval_applied,
    register_resource_destination,
)


@dataclass(frozen=True)
class ProviderWiring:
    """What the provider kind hands back: its service, and the internal-engine
    connection tied over it — the seam later kinds and the background workers
    resolve Coffer's own engine through, so none of them has to hold this
    kind's service to reach it."""

    service: ProviderService
    internal_connection: InternalEngineConnection
    #: The supervised local model proxy every agent on a connection calls.
    proxy: ModelProxyWiring
    #: Where a model's price on a provider comes from — shared by the usage
    #: meter and the Models section, so they never disagree.
    prices: ProviderPriceResolver
    #: The bundled price list and its daily refresh.
    price_list: PriceListSource
    price_refresh_task: asyncio.Task[None] | None = None

    async def stop_price_refresh(self) -> None:
        self.price_list.stop()
        if self.price_refresh_task is not None:
            self.price_refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.price_refresh_task


def wire_provider_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    secret_store: EncryptedSecretStore,
    agent_service: AgentService,
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
        secrets=secret_store,
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
        # The agents are pointed at the local model proxy, on the port
        # daemon-config.json names at the moment of each projection.
        proxy_root=proxy_root_now,
    )
    set_provider_service(provider_svc)
    # A key goes only to a base URL a person approved, and a key in use is
    # replaced only after approval (spec secret "Hold a secret for a new
    # destination until a person approves it").
    provider_svc.set_secret_boundary(get_secret_boundary())
    register_resource_destination("provider", _provider_secret_destination)

    # The projection into each agent's own config (ADR
    # one-level-triggered-reconciler-compares-parameters): judged by every key
    # Coffer owns there, on every pass — boot, period, and each hint (a sync
    # checkout hints every resource it changed, like an API write).
    reconciler.register(
        ProviderProjectionTarget(
            providers=provider_svc,
            agents=agent_service,
            projector=ProviderProjector(
                ConfigFileStore(), agents=agent_catalog, proxy_root=proxy_root_now
            ),
            store=ConfigFileStore(),
            deactivate=provider_svc.deactivate,
        )
    )
    # You set → local → from the provider's API → the bundled list (spec
    # provider-switching "Resolve each model's price from the provider, its
    # API, or the bundled list"). The list is read from the build, never
    # fetched per request: a daily refresh keeps a fresher copy of the list
    # (spec provider-switching "Refresh the bundled price list in the
    # background"), and every lookup reads whichever is fresher.
    price_list = PriceListSource(load_bundled_prices())
    set_price_list_source(price_list)
    prices = ProviderPriceResolver(provider_svc, price_list.current, reported_price_store())
    set_price_resolver(prices)
    refresh_task = (
        None
        if refresh_pinned_off()
        else asyncio.get_running_loop().create_task(price_list.run(), name="price-refresh")
    )
    proxy = wire_model_proxy(provider_svc, secret_store, reconciler)
    # An approved key reaches the proxy on the next state push, not before.
    on_approval_applied(proxy.schedule_refresh)
    return ProviderWiring(
        service=provider_svc,
        proxy=proxy,
        prices=prices,
        price_list=price_list,
        price_refresh_task=refresh_task,
        # Tied here because this is where both halves exist: the engine's rule
        # (application.engine) and the kind that knows which row is flagged.
        internal_connection=internal_engine_connection(provider_svc),
    )


def _provider_secret_destination(
    resource: Resource,
) -> tuple[SecretDestination, dict[str, str]] | None:
    cfg = ProviderConfig.model_validate(resource.config)
    if cfg.secret_ref is None:
        return None
    return provider_destination(resource.uid, resource.name, cfg), {"key": cfg.secret_ref}
