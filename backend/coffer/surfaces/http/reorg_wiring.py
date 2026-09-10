"""Composition-root helper that wires the notes tidy pass.

``LangchainAgenticReorg`` (the langgraph loop adapter) and a ``ProviderService``
wrapper are injected here, at a surfaces composition root (cross-kind imports
allowed). The pass's ``application/knowledge`` code reaches the loop only
through the kind-local ``AgenticReorgPort`` (Contract 9 keeps langgraph in
``infrastructure.chat``; Contract 5e keeps the knowledge kind off
``infrastructure.chat``).

This builds the service; ``tidy_wiring.py`` decides when it runs.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from coffer.application.knowledge.reorg import ReorgService
from coffer.application.knowledge.reorg_deps import reorg_collaborators_from_service
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.provider.service import ProviderService
from coffer.domain.provider.config import ResolvedConnection
from coffer.infrastructure.llm.agentic_reorg import LangchainAgenticReorg
from coffer.surfaces.http.knowledge.reorg_state import set_reorg_service


class _ModelSelector:
    """ModelSelectorPort adapter: resolves Coffer's internal-engine connection
    (the ``internal_default`` provider) for the tidy loop."""

    def __init__(self, provider_svc: ProviderService) -> None:
        self._svc = provider_svc

    async def get_default(self) -> ResolvedConnection | None:
        return await self._svc.resolve_internal_connection()


def wire_reorg(
    knowledge_service: KnowledgeService,
    provider_svc: ProviderService,
    credential_resolver: Callable[[str], str],
) -> ReorgService:
    """Construct and register the knowledge ReorgService — the tidy pass.

    Must be called AFTER ``wire_knowledge_kind`` (needs a live ``KnowledgeService``)
    and ``wire_provider_kind`` (needs a live ``ProviderService``). Exposes the
    service via ``set_reorg_service`` so both the ``organize`` route and the
    background trigger reach the SAME instance through ``get_reorg_service``.
    """
    deps = reorg_collaborators_from_service(knowledge_service)
    svc = ReorgService(
        resolve_store=deps.resolve_store,
        get_config=deps.get_config,
        store_ref=deps.store_ref,
        documents=deps.documents,
        retrieval=deps.retrieval,
        reconciler=deps.reconciler,
        audit=deps.audit,
        agent=LangchainAgenticReorg(),
        models=_ModelSelector(provider_svc),
        credential_resolver=credential_resolver,
        now=lambda: datetime.now(tz=UTC),
        embedding_resolver=deps.embedding_resolver,
    )
    set_reorg_service(svc)
    return svc
