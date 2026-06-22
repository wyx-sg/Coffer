"""Composition-root helper that wires the memory reorg service (spec 007).

Mirrors ``organize_wiring.py``: ``LangchainAgenticReorg`` (the langgraph loop
adapter) and a ``ProviderService`` wrapper are injected here, at a surfaces
composition root (cross-kind imports allowed). The reorg's
``application/memory`` code reaches the loop only through the memory-local
``AgenticReorgPort`` (Contract 9 keeps langgraph in ``infrastructure.chat``;
Contract 5e keeps memory off ``application.distill`` / ``infrastructure.chat``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from coffer.application.memory.reorg import ReorgService
from coffer.application.memory.reorg_deps import reorg_collaborators_from_service
from coffer.application.memory.service import MemoryService
from coffer.application.provider.service import ProviderService
from coffer.domain.provider.config import ResolvedConnection
from coffer.infrastructure.chat.agentic_reorg import LangchainAgenticReorg
from coffer.surfaces.http.memory.reorg_state import set_reorg_service


class _ModelSelector:
    """ModelSelectorPort adapter: resolves Coffer's internal-engine connection
    (the ``internal_default`` provider) for the reorg loop."""

    def __init__(self, provider_svc: ProviderService) -> None:
        self._svc = provider_svc

    async def get_default(self) -> ResolvedConnection | None:
        return await self._svc.resolve_internal_connection()


def wire_reorg(
    memory_service: MemoryService,
    provider_svc: ProviderService,
    credential_resolver: Callable[[str], str],
) -> ReorgService:
    """Construct and register the memory ReorgService.

    Must be called AFTER ``wire_memory_kind`` (needs a live ``MemoryService``)
    and ``wire_provider_kind`` (needs a live ``ProviderService``). Exposes the
    service via ``set_reorg_service`` so the ``reorg`` route reaches it through
    ``get_reorg_service``.
    """
    deps = reorg_collaborators_from_service(memory_service)
    svc = ReorgService(
        resolve_store=deps.resolve_store,
        get_config=deps.get_config,
        store_ref=deps.store_ref,
        documents=deps.documents,
        retrieval=deps.retrieval,
        reconciler=deps.reconciler,
        agent=LangchainAgenticReorg(),
        models=_ModelSelector(provider_svc),
        credential_resolver=credential_resolver,
        audit=deps.audit,
        now=lambda: datetime.now(tz=UTC),
        embedding_resolver=deps.embedding_resolver,
    )
    set_reorg_service(svc)
    return svc
