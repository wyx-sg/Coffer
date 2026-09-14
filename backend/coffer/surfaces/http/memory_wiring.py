"""Wiring for the one ``memory`` kind (spec memory FR-060..FR-063).

Mirrors ``knowledge_wiring.py`` + ``tidy_wiring.py`` combined: one service for
the derived tree itself (``MemoryService``), the one table it adds
(``OverrideRepository``), the L2 pull tool (``RecallService`` /
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
``MemoryService``/``DeliveryService``/``OverrideRepository`` need no internal
connection at all — recall is a literal scan over facts on disk (FR-032,
FR-052).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.memory.aggregate import AgentSource
from coffer.application.memory.builtin_recall_tool import register_recall_tool
from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.organise import organise_partition
from coffer.application.memory.organise_worker import OrganiseWorker
from coffer.application.memory.recall import RecallService
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.application.memory.sync_state import MemoryOverrideSyncState
from coffer.domain.agent.config import AgentConfig
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.llm.llm_completion import LangchainLlmCompletion
from coffer.infrastructure.persistence.memory_overrides_repo import OverrideRepository
from coffer.surfaces.http.dependencies import (
    set_memory_delivery_service,
    set_memory_override_repo,
    set_memory_service,
)
from coffer.surfaces.http.memory.organise_state import set_organise_runner

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import async_sessionmaker

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


def wire_memory_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    builtin_tools: BuiltinToolRegistry,
    provider_service: ProviderService,
    credential_resolver: Callable[[str], str],
    sm: async_sessionmaker[Any],
    agent_service: Any,
) -> tuple[MemoryService, OverrideRepository, DeliveryService]:
    """Wire the ``memory`` kind into the app; return its three services."""
    service = MemoryService(
        resources=resource_svc,
        audit=audit,
        agent_source_resolver=_agent_source,
    )
    set_memory_service(service)

    override_repo = OverrideRepository(sm)
    set_memory_override_repo(override_repo)

    # The developer's decisions are the one part of this layer that syncs — the
    # derived tree is rebuilt per machine and must not (spec vault-sync
    # "What does not sync").
    providers = getattr(app.state, "sync_state_providers", None)
    if providers is None:
        providers = []
        app.state.sync_state_providers = providers
    providers.append(MemoryOverrideSyncState(override_repo))

    recall_service = RecallService(memory=service, overrides=override_repo)
    register_recall_tool(builtin_tools, recall_service=recall_service)

    delivery_service = DeliveryService(
        agent_service=agent_service, audit=audit, store=ConfigFileStore()
    )
    set_memory_delivery_service(delivery_service)

    models = _InternalModelSelector(provider_service)
    completion = LangchainLlmCompletion()

    async def _organise(partition: str) -> Any:
        return await organise_partition(
            partition, models=models, completion=completion, credential_resolver=credential_resolver
        )

    set_organise_runner(_organise)
    app.state.memory_organise_runner = _organise

    app.state.kinds[KIND_MEMORY] = make_memory_kind(service)
    return service, override_repo, delivery_service


def start_organise_worker(app: FastAPI, resource_svc: ResourceService) -> None:
    """Start the organise sweep — on by default (``organise_worker.py``'s own
    docstring: the tree it rewrites is disposable, so there is no unattended-
    rewrite risk to gate behind an operator switch, unlike knowledge's tidy)."""

    async def _list_partitions() -> list[str]:
        return [r.name for r in await resource_svc.list(kind=KIND_MEMORY, enabled=True)]

    worker = OrganiseWorker(
        organise=app.state.memory_organise_runner, list_partitions=_list_partitions
    )
    app.state.memory_organise_worker_task = asyncio.create_task(worker.run_forever())


async def stop_organise_worker(app: FastAPI) -> None:
    task = getattr(app.state, "memory_organise_worker_task", None)
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
