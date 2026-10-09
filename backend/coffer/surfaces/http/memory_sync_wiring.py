"""Wiring for the memory sync (spec memory "Sync on an interval and on
demand").

Builds the sync service and its page view, sets the route dependencies, and
starts the worker: one sync at start, then on the operator's interval, while
both the ``memory`` feature and the ``memory_sync`` pass are on. The pass is
on by default (``domain.internal_engine_config``); the first sync on a machine
waits for the person to confirm its preview before it writes into an agent.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import replace

from coffer.application.audit_service import AuditService
from coffer.application.features import FeatureService
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.memory.sources import AgentSource
from coffer.application.memory.sync_service import MemorySyncService
from coffer.application.memory.sync_view import MemorySyncView
from coffer.application.memory.sync_worker import MemorySyncWorker
from coffer.application.resource_service import ResourceService
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.domain.agent.config import AgentConfig
from coffer.domain.features import MEMORY
from coffer.domain.internal_engine_config import MEMORY_SYNC
from coffer.infrastructure.memory.curation import launch_curation
from coffer.infrastructure.memory.readers import MEMORY_READERS
from coffer.infrastructure.memory.writers import MEMORY_WRITERS
from coffer.infrastructure.secret.detector import detect
from coffer.infrastructure.sync.identity import resolve_identity
from coffer.surfaces.http.memory.sync_dependencies import set_sync_services

logger = logging.getLogger(__name__)


def _home() -> str:
    return os.environ.get("HOME") or os.path.expanduser("~")


def _machine() -> str:
    try:
        return resolve_identity().machine_id or "unknown"
    except Exception:
        logger.warning("memory_sync.machine_id_unresolved", exc_info=True)
        return "unknown"


def _find_secret(text: str) -> str | None:
    found = detect(text)
    return found[0].rule if found else None


def wire_memory_sync(
    resource_svc: ResourceService,
    audit: AuditService,
    engine_config: InternalEngineConfigService,
) -> MemorySyncService:
    """Build the sync service and view and hand them to the routes."""

    async def _agents() -> list[AgentSource]:
        out = []
        for row in await resource_svc.list(kind="agent"):
            cfg = AgentConfig.model_validate(row.config)
            out.append(
                AgentSource(
                    agent=row.name,
                    agent_type=cfg.type.value,
                    config_dir=str(cfg.resolved_config_dir()),
                )
            )
        return out

    async def _stop_automatic(actor: str) -> None:
        current = (await engine_config.get()).upkeep(MEMORY_SYNC)
        if current.enabled:
            await engine_config.set_upkeep(
                MEMORY_SYNC, replace(current, enabled=False), actor=actor
            )

    service = MemorySyncService(
        agents=_agents,
        readers={r.agent_type: r for r in MEMORY_READERS},
        writers={w.agent_type: w for w in MEMORY_WRITERS},
        audit=audit,
        machine=_machine,
        home=_home,
        find_secret=_find_secret,
        stop_automatic=_stop_automatic,
    )
    view = MemorySyncView(
        service, machine=_machine, home=_home, audit=audit, launch=launch_curation
    )
    set_sync_services(service, view)
    return service


def start_memory_sync_worker(
    service: MemorySyncService,
    engine_config: InternalEngineConfigService,
    features: FeatureService,
) -> asyncio.Task[None]:
    async def _enabled() -> bool:
        if not features.is_enabled(MEMORY):
            return False
        return (await engine_config.get()).upkeep(MEMORY_SYNC).enabled

    async def _interval() -> int | None:
        return (await engine_config.get()).upkeep(MEMORY_SYNC).interval_s

    worker = MemorySyncWorker(sync=service.sync, is_enabled=_enabled, read_interval=_interval)
    return spawn_restarting(worker.run_forever, name="memory-sync")


async def stop_memory_sync_worker(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.debug("memory.sync_worker.stopped")


__all__ = ["start_memory_sync_worker", "stop_memory_sync_worker", "wire_memory_sync"]
