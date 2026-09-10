"""The scope substrate the consolidation organizer is built from.

Kept out of ``service.py`` (file-size budget) and out of ``organizer.py`` (so
the service does not import the organizer). ``collaborators_from_service``
projects a live ``KnowledgeService`` onto the plain collaborators the
``OrganizerService`` needs — the composition root then injects the LLM port +
model selector on top.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coffer.application.knowledge.ports import KnowledgeDocumentRepo
from coffer.application.knowledge.retrieval import EmbeddingResolver, KnowledgeRetrieval
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.sync import KnowledgeReconciler
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.knowledge.scope import ResolvedScope
from coffer.domain.knowledge.scope_config import KnowledgeConfig


@dataclass(frozen=True)
class OrganizerCollaborators:
    """The plain collaborators the organizer is composed from (no LLM here)."""

    resolve_store: Callable[[str], Awaitable[ResolvedScope]]
    get_config: Callable[[str], Awaitable[KnowledgeConfig]]
    store_ref: Callable[[str, str], StoreRef]
    documents: KnowledgeDocumentRepo
    retrieval: KnowledgeRetrieval
    reconciler: KnowledgeReconciler
    embedding_resolver: EmbeddingResolver


def collaborators_from_service(svc: KnowledgeService) -> OrganizerCollaborators:
    """Project a live ``KnowledgeService`` onto the organizer's collaborators."""
    return OrganizerCollaborators(
        resolve_store=svc.resolved_scope,
        get_config=svc.get_config,
        store_ref=svc._recall.store_ref,
        documents=svc._documents,
        retrieval=svc._retrieval,
        reconciler=svc._reconciler,
        embedding_resolver=svc._resolve_embedding,
    )
