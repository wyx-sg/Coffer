"""Composition-root helper that wires the memory consolidation organizer.

Clones ``distill_wiring.py``: the langchain one-shot completion adapter
(``LangchainLlmCompletion``) and a ``ModelService`` wrapper are injected here, at
a surfaces composition root (cross-kind imports allowed). The organizer's
``application/memory`` code reaches the LLM only through the memory-local
``LlmCompletionPort`` (Contract 9 keeps langchain in ``infrastructure.chat``;
Contract 5e keeps memory off ``application.distill``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from coffer.application.chat.model_service import ModelService
from coffer.application.memory.organizer import OrganizerService
from coffer.application.memory.organizer_deps import collaborators_from_service
from coffer.application.memory.service import MemoryService
from coffer.domain.chat.model import ModelConfig
from coffer.infrastructure.chat.llm_completion import LangchainLlmCompletion
from coffer.surfaces.http.memory.organize_state import set_organizer_service


class _ModelSelector:
    """ModelSelectorPort adapter: thin passthrough to ModelService.get_default."""

    def __init__(self, model_svc: ModelService) -> None:
        self._svc = model_svc

    async def get_default(self) -> ModelConfig | None:
        return await self._svc.get_default()


def wire_organize(
    memory_service: MemoryService,
    model_svc: ModelService,
    credential_resolver: Callable[[str], str],
) -> OrganizerService:
    """Construct and register the memory OrganizerService.

    Must be called AFTER ``wire_memory_kind`` (needs a live ``MemoryService``)
    and ``wire_chat`` (needs a live ``ModelService``). Exposes the service via
    ``set_organizer_service`` so the ``organize`` route reaches it through
    ``get_organizer_service``.
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
        models=_ModelSelector(model_svc),
        credential_resolver=credential_resolver,
        audit=deps.audit,
        now=lambda: datetime.now(tz=UTC),
        embedding_resolver=deps.embedding_resolver,
    )
    set_organizer_service(svc)
    return svc
