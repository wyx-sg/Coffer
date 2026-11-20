"""Compose memory (ADR keep-memory-in-one-place-agents-write-themselves).

The hub's services for the Memory page and the tidy; Coffer's session-start
hook as a reconcile target, converged again whenever memory is switched; the
one-time clean-up of what an older build wrote (its hub entries converted to
topics, its copies taken out of the agents' own memory); and a slow loop that
closes a tidy whose agent went quiet.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import pathlib
from dataclasses import dataclass

from coffer.application.features import FeatureService
from coffer.application.memory.hook_target import TARGET, MemoryHookTarget
from coffer.application.memory.service import MemoryService
from coffer.application.memory.tidy import MemoryTidy
from coffer.application.provider.cli_path import default_coffer_cli_resolver
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.application.runtime.wakeable import WakeableLoop
from coffer.domain.agent.config import AgentConfig
from coffer.domain.features import MEMORY
from coffer.domain.reconcile import Trigger
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.memory.hub_store import HubStore
from coffer.infrastructure.memory.legacy import remove_old_copies
from coffer.surfaces.http.memory.dependencies import set_memory_services

_log = logging.getLogger(__name__)

#: How often an open tidy is checked for an agent that went quiet.
TIDY_CHECK_S = 300.0


class _Agents:
    """What the hook target and the clean-up read of the agent registry."""

    def __init__(self, agents: object) -> None:
        self._agents = agents

    async def list(self) -> list[Resource]:
        return await self._agents.list()  # type: ignore[attr-defined,no-any-return]


@dataclass(frozen=True)
class MemoryWiring:
    service: MemoryService
    tidy: MemoryTidy


def _config_dirs(rows: list[Resource]) -> list[pathlib.Path]:
    dirs: list[pathlib.Path] = []
    for row in rows:
        try:
            dirs.append(AgentConfig.model_validate(row.config).resolved_config_dir())
        except Exception:
            continue
    return dirs


async def wire_memory(
    *, reconciler: Reconciler, agents: object, features: FeatureService
) -> MemoryWiring:
    """Build the services and register the hook target; run the clean-up of an
    older build's state."""
    hub = HubStore()
    service = MemoryService(hub)
    tidy = MemoryTidy(hub)
    set_memory_services(service, tidy)
    registry = _Agents(agents)
    reconciler.register(
        MemoryHookTarget(
            agents=registry,
            store=ConfigFileStore(),
            cli_resolver=default_coffer_cli_resolver,
            enabled=lambda: features.is_enabled(MEMORY),
        )
    )

    async def _on_switch(key: str, _enabled: bool) -> None:
        if key == MEMORY:
            await reconciler.run(targets=[TARGET], trigger=Trigger.SWITCH)

    features.subscribe(_on_switch)

    # What an older build left: its copies in the agents' own memory (handed
    # twice otherwise) and its one-file-per-memory hub entries.
    try:
        rows = await registry.list()
        await asyncio.to_thread(remove_old_copies, _config_dirs(rows))
        await asyncio.to_thread(hub.convert_legacy)
    except Exception:
        _log.warning("memory.legacy_cleanup_failed", exc_info=True)
    return MemoryWiring(service=service, tidy=tidy)


def start_memory_worker(tidy: MemoryTidy, features: FeatureService) -> asyncio.Task[None]:
    """Close a tidy whose agent went quiet; the lifespan cancels the task."""

    async def _pass(_poked: bool) -> None:
        if features.is_enabled(MEMORY):
            await tidy.expire()

    loop = WakeableLoop(
        "memory-tidy", _pass, fallback=TIDY_CHECK_S, failure_event="memory.tidy.tick_failed"
    )
    return spawn_restarting(loop.serve, name="memory-tidy")


async def stop_memory_worker(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


__all__ = ["MemoryWiring", "start_memory_worker", "stop_memory_worker", "wire_memory"]
