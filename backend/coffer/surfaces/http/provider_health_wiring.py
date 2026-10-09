"""Composition of each connection's health (spec provider-switching "Know each
connection's health without opening it").

Built after the chat wiring, because the check lists models through the
introspection service built there. The service reads and writes the verdicts
in ``derived.db``, hears every resource write (an edited connection is checked
again, a deleted one forgotten), is handed what the usage ingest read from the
model proxy's spool, and announces a moved status twice: as a ``provider``
envelope on the event stream (the provider list refetches) and as a nudge to
the attention watcher (the Overview recomputes). Its sweep runs as a task the
daemon's supervisor restarts; ``COFFER_PROVIDER_HEALTH=off`` leaves the sweep
and the re-checks out (the test suite), while a check someone asks for still
runs.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.provider.health import ProviderHealthService
from coffer.application.provider.introspection import ModelIntrospectionService
from coffer.application.provider.ports import ModelList
from coffer.application.provider.secret_gate import require_key
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource
from coffer.infrastructure.provider.health_repo import ProviderHealthRepo
from coffer.surfaces.http.event_wiring import EventStream
from coffer.surfaces.http.kind_wiring import KindWirings
from coffer.surfaces.http.provider_health_routes import set_provider_health_service

#: Set to ``off`` to check only when asked (no sweep, no re-check after an edit).
BACKGROUND_ENV = "COFFER_PROVIDER_HEALTH"

KIND = "provider"


def background_checks_on() -> bool:
    return os.environ.get(BACKGROUND_ENV, "").strip().lower() != "off"


def wire_provider_health(
    derived_sm: async_sessionmaker[AsyncSession],
    kinds: KindWirings,
    introspection: ModelIntrospectionService,
    events: EventStream,
) -> ProviderHealthService:
    """Build the health service, connect it, and start its sweep."""
    providers = kinds.provider.service

    async def list_models(protocol: str, base_url: str | None, ref: str | None) -> ModelList:
        return await introspection.list_models(provider=protocol, base_url=base_url, secret_ref=ref)

    async def authorize(resource: Resource, cfg: ProviderConfig) -> None:
        await require_key(providers, resource.uid, resource.name, cfg)

    service = ProviderHealthService(
        store=ProviderHealthRepo(derived_sm),
        connections=providers,
        list_models=list_models,
        authorize=authorize,
        background=background_checks_on(),
    )

    def changed(uid: str) -> None:
        events.broker.publish(KIND, uid)
        events.watcher.nudge()

    service.on_change = changed
    events.late_sinks.append(service.on_changed)
    kinds.usage.ingest.observe = service.observe
    set_provider_health_service(service)
    spawn_restarting(service.run, name="provider-health")
    return service


__all__ = ["BACKGROUND_ENV", "background_checks_on", "wire_provider_health"]
