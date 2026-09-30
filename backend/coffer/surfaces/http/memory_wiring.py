"""Wiring for the one ``memory`` kind (spec memory).

Mirrors ``knowledge_wiring.py`` + ``curation_wiring.py`` combined: one service for
the derived tree and its two passes (``MemoryService``), the memory root the
gateway's handshake names, and the delivery hook half (``DeliveryService``),
which the agent's Coffer connection installs.

**The three internal-engine arguments on ``MemoryService`` are the point of
this module.** The distil pass reaches a model through the same injected ports
every other internal-LLM consumer here uses — a completion port, a
``ModelSelectorPort`` over Coffer's own engine, and a **secret resolver**.
All three default to ``None`` on the service, and that default is the
mechanical pass of "Distil mechanically with no internal connection": each raw
entry becomes a note of its own and the index is still written. Which means a
resolver forgotten here does not fail loudly; it degrades every pass to "wrote
the index only" and says nothing, the model call having failed for want of a
key it was never given. ``curation_wiring.wire_curation``
takes the resolver as a required parameter for the same reason, and this module
follows it exactly: ``wire_memory_kind`` cannot be called without one.

The selector is **handed in** rather than derived here, now that resolving the
internal connection is Coffer's own engine's job
(``application.engine.resolve``) and not something each kind's wiring works out
from the provider service for itself.

The kind exposes no MCP tool (spec memory "Expose no memory tool and name the
memory root at session start"): it registers the memory root as an agent
directory instead, which the handshake and the ``coffer-guide`` skill name. The
distil sweep it starts is on by default, because it only
ever rewrites a tree that can be rebuilt from the agents' own memories (see
``distil_worker.py``).

Nothing here can fail to build: with no internal connection configured the
selector just resolves to ``None`` per call, and ``MemoryService`` /
``DeliveryService`` need no internal connection at all.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.application.agent.service import AgentService
from coffer.application.builtin_tools import AgentDirectory, BuiltinToolRegistry
from coffer.application.engine_ports import ModelSelectorPort
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.memory.aggregate import AgentSource
from coffer.application.memory.aggregate_worker import AggregateWorker
from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.delivery_reconcile import (
    ConnectedAgents,
    DeliveryHookTarget,
)
from coffer.application.memory.delivery_stats import DeliveryStatsService
from coffer.application.memory.distil import DistilResult
from coffer.application.memory.distil_worker import WORKER_ACTOR, DistilWorker
from coffer.application.memory.hook_service import MemoryHookService
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.ledger_restore import restore_from_audit
from coffer.application.memory.retrieval import RetrievalService
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.application.memory.session_ledger import SessionLedger
from coffer.application.memory.triggers import TriggerService
from coffer.application.memory.turn_retrieval import TurnRetrieval
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.internal_engine_config import AGGREGATE, DISTIL
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.llm.llm_completion import LangchainLlmCompletion
from coffer.infrastructure.memory import paths as memory_paths
from coffer.surfaces.http.engine_config_composition import read_internal_engine_timeout
from coffer.surfaces.http.memory.dependencies import (
    set_memory_hook_service,
    set_memory_service,
    set_memory_stats_service,
    set_memory_trigger_service,
)
from coffer.surfaces.http.memory.distil_state import DistilRunner

if TYPE_CHECKING:
    from fastapi import FastAPI

    from coffer.application.audit_service import AuditService
    from coffer.application.resource_service import ResourceService
    from coffer.domain.resource import Resource

logger = logging.getLogger(__name__)


def _agent_source(resource: Resource) -> AgentSource:
    """``AgentSourceResolver`` — a registered agent Resource, reduced to what
    aggregation needs (its type + effective config dir), mirroring
    ``agent_skill_wiring.py``'s own cross-kind resolvers built the same way."""
    cfg = AgentConfig.model_validate(resource.config)
    return AgentSource(
        # The NAME, deliberately. This value becomes an entry's ``Origin.agent``
        # — a line a person reads in a note's provenance ("origin: claude-code
        # <- ~/.claude/...") — not a reference anything resolves later. An
        # origin describes what was true when the entry was captured, so a uid
        # here would make the record unreadable to buy a stability it has no
        # use for.
        agent=resource.name,
        agent_type=cfg.type.value,
        config_dir=str(cfg.resolved_config_dir()),
    )


@dataclass(frozen=True)
class MemoryWiring:
    """What the memory kind hands back: its two services, the distil runner
    the background worker sweeps with, and the per-prompt retrieval a channel
    turn reads through (``memory_turn_wiring``)."""

    service: MemoryService
    delivery_service: DeliveryService
    distil: DistilRunner
    turn_retrieval: TurnRetrieval


def register_delivery_hook_target(
    reconciler: Reconciler, delivery: DeliveryService, connected: ConnectedAgents
) -> None:
    """Register the memory delivery hook with the reconciler.

    Every pass — boot, period, hint, a person applying from the drift view —
    then compares each installed hook's whole command with what this build
    would install (spec memory "Repair stale delivery hooks"). ``connected`` is
    the agent kind's answer to which agents carry Coffer's gateway entry.
    """
    reconciler.register(DeliveryHookTarget(delivery=delivery, connected=connected))


def wire_memory_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    builtin_tools: BuiltinToolRegistry,
    models: ModelSelectorPort,
    secret_resolver: Callable[[str], str],
    agent_service: AgentService,
    agent_catalog: AgentCatalog,
) -> MemoryWiring:
    """Wire the ``memory`` kind into the app; return what it built."""
    service = MemoryService(
        resources=resource_svc,
        audit=audit,
        agent_source_resolver=_agent_source,
        # The agents' memory-reader facets.
        readers=agent_catalog.memory_readers(),
        # The distil pass's model half. All three travel together or not at
        # all: a completion port with no secret resolver behind it reaches
        # the provider and is refused the key, which "Distil mechanically with no
        # internal connection" then reads as "no internal connection" and
        # answers with the mechanical pass. See the module docstring — this is
        # the silent degradation the trio prevents.
        completion=LangchainLlmCompletion(),
        model_selector=models,
        secret_resolver=secret_resolver,
        read_timeout=read_internal_engine_timeout,
    )
    set_memory_service(service)

    # Nothing in this layer syncs: the whole tree under ``~/.coffer/derived/memory/``
    # is derived from the agents installed on THIS machine and is rebuilt per
    # machine (spec vault-sync "Keep reach machine-local").

    # No tool: an agent finds a note by searching this directory with its own
    # tools, and the handshake names it.
    builtin_tools.register_directory(
        AgentDirectory(name="memory", path=lambda: str(memory_paths.memory_root()))
    )

    # The hook adapters are the delivery-hook entries of the agents'
    # projection facets.
    delivery_service = DeliveryService(
        agent_service=agent_service, audit=audit, store=ConfigFileStore(), catalog=agent_catalog
    )

    # Prompt-time retrieval, the once-per-session guard and the delivery views.
    triggers = TriggerService(audit=audit)
    # Rebuilt from the delivery fires in the audit log after a restart.
    ledger = SessionLedger(restore=lambda led: restore_from_audit(led, audit))
    retrieval = RetrievalService(service, ledger)
    set_memory_hook_service(
        MemoryHookService(
            memory=service,
            delivery=delivery_service,
            retrieval=retrieval,
            triggers=triggers,
            ledger=ledger,
        )
    )
    set_memory_trigger_service(triggers)
    set_memory_stats_service(
        DeliveryStatsService(memory=service, delivery=delivery_service, audit=audit)
    )
    # Distil proposes triggers unarmed; only a person arms one.
    service.set_trigger_proposer(triggers.propose)

    app.state.kinds[KIND_MEMORY] = make_memory_kind(service)
    return MemoryWiring(
        service=service,
        delivery_service=delivery_service,
        distil=service.distil,
        turn_retrieval=TurnRetrieval(retrieval, delivery_service, agent_service),
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
    """Start the aggregation pass — a catch-up on boot, then on a timer.

    Spec memory "Aggregate on an interval and on demand".

    On by default: a pass reads the agents' own memory files and writes only
    the derived tree, and "Skip unchanged sources" makes a pass over unchanged
    sources nearly free. The Sync button and ``coffer memory sync`` stay: this makes the
    layer current without being asked, it does not replace asking.

    Both halves of "on a timer" are the operator's (spec internal-engine "Apply a
    changed switch or interval without a restart"), and both are read PER PASS
    rather than captured here — the setting converges from other machines
    through vault sync, so a value read once at boot would be stale without
    anything on this machine having changed.
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


def start_distil_worker(
    distil: DistilRunner,
    resource_svc: ResourceService,
    engine_config: InternalEngineConfigService,
) -> asyncio.Task[None]:
    """Start the distil sweep — on by default, because the tree it rewrites is
    disposable ("Keep the memory tree derived and local": delete it and
    re-running reproduces it). On by default is not the same as unstoppable, though: the
    operator can switch it off and re-time it like any other pass.
    Returns the task; the lifespan cancels it at shutdown."""

    async def _list_partitions() -> list[str]:
        # Uids, not names: the sweep and Update memory are two writers over
        # one directory and claim the same upkeep-runs key, so
        # both must spell the partition the way that cannot change between
        # them reading it ("Run one distil pass per partition at a time", ADR
        # resource-identity-is-an-immutable-uid).
        # The pass resolves the row for the directory it rewrites.
        return [r.uid for r in await resource_svc.list(kind=KIND_MEMORY, enabled=True)]

    async def _scheduled(uid: str) -> DistilResult:
        """The sweep's own actor, fixed here rather than defaulted in the
        service: ``memory_distilled`` rows written by this timer must be
        readable as the timer's, or the audit log cannot answer whether a
        partition was last rewritten because somebody asked ("Audit every
        lifecycle act")."""
        return await distil(uid, actor=WORKER_ACTOR)

    worker = DistilWorker(
        distil=_scheduled,
        list_partitions=_list_partitions,
        is_enabled=_upkeep_enabled(engine_config, DISTIL),
        read_interval=_upkeep_interval(engine_config, DISTIL),
    )
    return asyncio.create_task(worker.run_forever())


async def stop_distil_worker(task: asyncio.Task[None]) -> None:
    """Cancel the sweep and wait for it to acknowledge; a pending pass is
    dropped, not fired (the next boot sweeps everything)."""
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.debug("memory.distil_worker.stopped")
