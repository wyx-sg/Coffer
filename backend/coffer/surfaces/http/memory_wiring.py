"""Wiring for the one ``memory`` kind (spec memory FR-060..FR-063).

Mirrors ``knowledge_wiring.py`` + ``tidy_wiring.py`` combined: one service for
the derived tree itself (``MemoryService``), the one table it adds
the L2 pull tool (``RecallService`` /
``coffer__recall``), and the explicit-install delivery half
(``DeliveryService``). The organise pass rides the same internal connection
every other internal-LLM consumer in this layer uses; the model resolver below
is deliberately re-derived here rather than imported from
``knowledge_wiring.py`` — its own equivalent is private, and this project's
own convention (``application.memory.builtin_recall_tool``'s module
docstring) is to duplicate a few lines rather than let two kind's wiring
modules import each other.

The kind is wired before the MCP kind so the gateway advertises
``coffer__recall``; the organise sweep it starts is on by default, because
unlike knowledge's tidy it only ever rewrites a tree that can be rebuilt from
the agents' own memories (see ``organise_worker.py``).

Nothing here can fail to build: with no internal connection configured the
model factory just resolves to ``None`` per call, and ``RecallService``/
``MemoryService``/``DeliveryService`` need no internal
connection at all — recall is a literal scan over facts on disk (FR-032,
FR-052).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.application.agent.service import AgentService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.memory.aggregate import AgentSource
from coffer.application.memory.aggregate_worker import AggregateWorker
from coffer.application.memory.builtin_recall_tool import register_recall_tool
from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.organise import OrganiseResult, organise_partition
from coffer.application.memory.organise_worker import OrganiseWorker
from coffer.application.memory.recall import RecallService
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.internal_engine_config import AGGREGATE, ORGANISE
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.llm.llm_completion import LangchainLlmCompletion
from coffer.surfaces.http.memory.dependencies import (
    set_memory_delivery_service,
    set_memory_service,
)
from coffer.surfaces.http.memory.organise_state import OrganiseRunner, set_organise_runner

if TYPE_CHECKING:
    from fastapi import FastAPI

    from coffer.application.audit_service import AuditService
    from coffer.application.provider.service import ProviderService
    from coffer.application.resource_service import ResourceService
    from coffer.domain.provider.config import ResolvedConnection
    from coffer.domain.resource import Resource

logger = logging.getLogger(__name__)


def _agent_source(resource: Resource) -> AgentSource:
    """``AgentSourceResolver`` — a registered agent Resource, reduced to what
    aggregation needs (its type + effective config dir), mirroring
    ``agent_skill_wiring.py``'s own cross-kind resolvers built the same way."""
    cfg = AgentConfig.model_validate(resource.config)
    return AgentSource(
        agent=resource.name,
        agent_type=cfg.type.value,
        config_dir=str(cfg.resolved_config_dir()),
    )


class _InternalModelSelector:
    """Structural ``ModelSelectorPort`` adapter over ``ProviderService`` —
    what ``organise_partition`` needs to reach the internal connection."""

    def __init__(self, provider_service: ProviderService) -> None:
        self._provider_service = provider_service

    async def get_default(self) -> ResolvedConnection | None:
        return await self._provider_service.resolve_internal_connection()


@dataclass(frozen=True)
class MemoryWiring:
    """What the memory kind hands back: its three services and the organise
    runner the background worker sweeps with."""

    service: MemoryService
    delivery_service: DeliveryService
    organise: OrganiseRunner


def wire_memory_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    builtin_tools: BuiltinToolRegistry,
    provider_service: ProviderService,
    credential_resolver: Callable[[str], str],
    agent_service: AgentService,
) -> MemoryWiring:
    """Wire the ``memory`` kind into the app; return what it built."""
    service = MemoryService(
        resources=resource_svc,
        audit=audit,
        agent_source_resolver=_agent_source,
    )
    set_memory_service(service)

    # Nothing in this layer syncs: the whole tree under ``~/.coffer/memory/``
    # is derived from the agents installed on THIS machine and is rebuilt per
    # machine (spec vault-sync "What does not sync").

    recall_service = RecallService(memory=service)
    register_recall_tool(builtin_tools, recall_service=recall_service)

    delivery_service = DeliveryService(
        agent_service=agent_service, audit=audit, store=ConfigFileStore()
    )
    set_memory_delivery_service(delivery_service)

    models = _InternalModelSelector(provider_service)
    completion = LangchainLlmCompletion()

    async def _organise(partition: str) -> OrganiseResult:
        return await organise_partition(
            partition, models=models, completion=completion, credential_resolver=credential_resolver
        )

    set_organise_runner(_organise)

    app.state.kinds[KIND_MEMORY] = make_memory_kind(service)
    return MemoryWiring(
        service=service,
        delivery_service=delivery_service,
        organise=_organise,
    )


def _upkeep_enabled(
    engine_config: InternalEngineConfigService, pass_name: str
) -> Callable[[], Awaitable[bool]]:
    """Reads the pass's switch, every pass. See ``start_aggregate_worker``."""

    async def _enabled() -> bool:
        return (await engine_config.get()).upkeep(pass_name).enabled

    return _enabled


def _upkeep_interval(
    engine_config: InternalEngineConfigService, pass_name: str
) -> Callable[[], Awaitable[int | None]]:
    """Reads the pass's interval, re-read while a wait is already running so a
    change in Settings lands within a slice rather than at the end of it."""

    async def _interval() -> int | None:
        return (await engine_config.get()).upkeep(pass_name).interval_s

    return _interval


def start_aggregate_worker(
    service: MemoryService, engine_config: InternalEngineConfigService
) -> asyncio.Task[None]:
    """Start the aggregation pass (FR-007) — a catch-up on boot, then on a timer.

    On by default: a pass reads the agents' own memory files and writes only
    the derived tree, and FR-006 makes a pass over unchanged sources nearly
    free. The Sync button and ``coffer memory sync`` stay: this makes the
    layer current without being asked, it does not replace asking.

    Both halves of "on a timer" are the operator's (spec provider-switching
    E3a), and both are read PER PASS rather than captured here — the setting
    converges from other machines through vault sync, so a value read once at
    boot would be stale without anything on this machine having changed.
    Returns the task; the lifespan cancels it at shutdown.
    """
    worker = AggregateWorker(
        aggregate=service.aggregate,
        is_enabled=_upkeep_enabled(engine_config, AGGREGATE),
        read_interval=_upkeep_interval(engine_config, AGGREGATE),
    )
    return asyncio.create_task(worker.run_forever())


async def stop_aggregate_worker(task: asyncio.Task[None]) -> None:
    """Cancel the pass and wait for it to acknowledge; a pending pass is
    dropped, not fired (the next boot aggregates everything again)."""
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.debug("memory.aggregate_worker.stopped")


def start_organise_worker(
    organise: OrganiseRunner,
    resource_svc: ResourceService,
    engine_config: InternalEngineConfigService,
) -> asyncio.Task[None]:
    """Start the organise sweep — on by default, because the tree it rewrites is
    disposable (FR-023: delete it and re-running reproduces it), unlike
    knowledge's tidy. On by default is not the same as unstoppable, though: the
    operator can switch it off and re-time it like any other pass.
    Returns the task; the lifespan cancels it at shutdown."""

    async def _list_partitions() -> list[str]:
        return [r.name for r in await resource_svc.list(kind=KIND_MEMORY, enabled=True)]

    worker = OrganiseWorker(
        organise=organise,
        list_partitions=_list_partitions,
        is_enabled=_upkeep_enabled(engine_config, ORGANISE),
        read_interval=_upkeep_interval(engine_config, ORGANISE),
    )
    return asyncio.create_task(worker.run_forever())


async def stop_organise_worker(task: asyncio.Task[None]) -> None:
    """Cancel the sweep and wait for it to acknowledge; a pending pass is
    dropped, not fired (the next boot sweeps everything)."""
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.debug("memory.organise_worker.stopped")
