"""Composition-root helper that wires the memory consolidation organizer.

Clones ``distill_wiring.py``: the langchain one-shot completion adapter
(``LangchainLlmCompletion``) and a ``ProviderService`` wrapper are injected here,
at a surfaces composition root (cross-kind imports allowed). The organizer's
``application/memory`` code reaches the LLM only through the memory-local
``LlmCompletionPort`` (Contract 9 keeps langchain in ``infrastructure.chat``;
Contract 5e keeps memory off ``application.distill``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from coffer.application.memory.organizer import OrganizerService
from coffer.application.memory.organizer_deps import collaborators_from_service
from coffer.application.memory.service import MemoryService
from coffer.application.provider.service import ProviderService
from coffer.domain.provider.config import ResolvedConnection
from coffer.infrastructure.chat.llm_completion import LangchainLlmCompletion
from coffer.surfaces.http.memory.organize_state import set_organizer_service


class _ModelSelector:
    """ModelSelectorPort adapter: resolves Coffer's internal-engine connection
    (the ``internal_default`` provider) for the organizer."""

    def __init__(self, provider_svc: ProviderService) -> None:
        self._svc = provider_svc

    async def get_default(self) -> ResolvedConnection | None:
        return await self._svc.resolve_internal_connection()


def wire_organize(
    memory_service: MemoryService,
    provider_svc: ProviderService,
    credential_resolver: Callable[[str], str],
) -> OrganizerService:
    """Construct and register the memory OrganizerService.

    Must be called AFTER ``wire_memory_kind`` (needs a live ``MemoryService``)
    and ``wire_provider_kind`` (needs a live ``ProviderService``). Exposes the
    service via ``set_organizer_service`` so the ``organize`` route reaches it
    through ``get_organizer_service``.
    """
    deps = collaborators_from_service(memory_service)
    svc = OrganizerService(
        resolve_store=deps.resolve_store,
        get_config=deps.get_config,
        store_ref=deps.store_ref,
        documents=deps.documents,
        retrieval=deps.retrieval,
        reconciler=deps.reconciler,
        llm=LangchainLlmCompletion(),
        models=_ModelSelector(provider_svc),
        credential_resolver=credential_resolver,
        audit=deps.audit,
        now=lambda: datetime.now(tz=UTC),
        embedding_resolver=deps.embedding_resolver,
    )
    set_organizer_service(svc)
    return svc
