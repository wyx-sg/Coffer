"""Composition-root wiring for the ``provider`` kind (spec provider-switching).

Registers the kind into ``app.state.kinds`` (so it gets CRUD + audit + sync for
free) and constructs the :class:`ProviderService`, exposed via the DI getter.
Call this AFTER ``wire_agent_and_skill_kinds`` — the service needs the agent
service to know which agents to project into, and the lifespan passes it in.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from dataclasses import dataclass

from fastapi import FastAPI

from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.engine.resolve import InternalEngineConnection
from coffer.application.features import FeatureService
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.prices import ProviderPriceResolver
from coffer.application.provider.projection_reconcile import (
    TARGET as PROJECTION_TARGET,
)
from coffer.application.provider.projection_reconcile import ProviderProjectionTarget
from coffer.application.provider.projector import ProviderProjector
from coffer.application.provider.secret_gate import provider_destination
from coffer.application.provider.service import ProviderService
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.resource_service import ResourceService
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.features import MODELS
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.reconcile import Outcome, Trigger
from coffer.domain.resource import Resource
from coffer.domain.secrets import SecretDestination
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.provider.reported_prices import shared_store as reported_price_store
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.infrastructure.usage.bundled_prices import load_bundled_prices
from coffer.infrastructure.usage.price_refresh import (
    PriceListSource,
    refresh_enabled,
    refresh_pinned_off,
)
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

_log = logging.getLogger(__name__)


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
    """Wire the ``provider`` kind (spec provider-switching) into the app.

    Everything here that runs without a request follows the ``models`` feature
    (spec experimental-features "Close every surface of a switched-off
    feature"): the projection into the agents, the local model proxy's state
    and the price list's daily refresh."""
    features = app.state.feature_service

    def models_on() -> bool:
        return bool(features.is_enabled(MODELS))

    # Handed the resource service so a direct write cannot flag a second
    # internal default (spec provider-switching "Keep at most one internal
    # default connection").
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
            clear_choice=provider_svc.clear_agent_connection,
            is_enabled=models_on,
        )
    )
    # You set → local → from the provider's API → the bundled list (spec
    # provider-switching "Resolve each model's price from the provider, its
    # API, or the bundled list"). The list is read from the build, never
    # fetched per request: a daily refresh keeps a fresher copy of the list
    # (spec provider-switching "Refresh the bundled price list in the
    # background"), and every lookup reads whichever is fresher.
    price_list = PriceListSource(
        load_bundled_prices(), enabled=lambda: models_on() and refresh_enabled()
    )
    set_price_list_source(price_list)
    prices = ProviderPriceResolver(provider_svc, price_list.current, reported_price_store())
    set_price_resolver(prices)
    refresh_task = (
        None if refresh_pinned_off() else spawn_restarting(price_list.run, name="price-refresh")
    )
    proxy = wire_model_proxy(provider_svc, secret_store, reconciler, enabled=models_on)
    _follow_models_switch(reconciler, features, proxy)
    _revoke_token_on_agent_delete(app, proxy)
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


def _follow_models_switch(
    reconciler: Reconciler, features: FeatureService, proxy: ModelProxyWiring
) -> None:
    """Withdraw or restore the agents' projections, and re-push the proxy's
    state, whenever ``models`` is switched.

    The projection pass reads the state ``models`` is in when it runs (off
    withdraws Coffer's keys from every agent, on projects each agent's connection
    again; ``Trigger.SWITCH`` is the warrant for both) and the proxy serves
    nothing while it is off. Nothing here fails the switch.
    """

    async def _on_switch(key: str, _enabled: bool) -> None:
        if key != MODELS:
            return
        try:
            report = await reconciler.run(targets=[PROJECTION_TARGET], trigger=Trigger.SWITCH)
        except Exception:
            _log.exception("models_switch.failed")
            return
        for failure in report.failures:
            _log.warning("models_switch %s: %s", failure.target, failure.error)
        for result in report.results:
            if result.outcome is Outcome.FAILED:
                _log.warning("models_switch %s: %s", result.change.id, result.error)
        proxy.schedule_refresh()

    features.subscribe(_on_switch)


def _revoke_token_on_agent_delete(app: FastAPI, proxy: ModelProxyWiring) -> None:
    """A removed agent's proxy token is deleted with it. The agent kind is
    registered before the proxy exists, so its delete hook is chained here
    rather than where the kind is built."""
    kind = app.state.kinds["agent"]
    previous = kind.on_delete

    async def on_delete(agent: Resource) -> None:
        if previous is not None:
            await previous(agent)
        await proxy.tokens.revoke(agent.uid)

    app.state.kinds["agent"] = dataclasses.replace(kind, on_delete=on_delete)


def _provider_secret_destination(
    resource: Resource,
) -> tuple[SecretDestination, dict[str, str]] | None:
    cfg = ProviderConfig.model_validate(resource.config)
    if cfg.secret_ref is None:
        return None
    return provider_destination(resource.uid, resource.name, cfg), {"key": cfg.secret_ref}
