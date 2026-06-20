"""The memory substrate the consolidation organizer is built from.

Kept out of ``service.py`` (file-size budget) and out of ``organizer.py`` (so
the service does not import the organizer). ``collaborators_from_service``
projects a live ``MemoryService`` onto the plain collaborators the
``OrganizerService`` needs — the composition root then injects the LLM port +
model selector on top.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.retrieval import EmbeddingResolver, KnowledgeRetrieval
from coffer.application.memory.ports import MemoryDocumentRepo
from coffer.application.memory.service import MemoryService
from coffer.application.memory.sync import MemoryReconciler
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.scope import ResolvedScope


@dataclass(frozen=True)
class OrganizerCollaborators:
    """The plain collaborators the organizer is composed from (no LLM here)."""

    resolve_store: Callable[[str], Awaitable[ResolvedScope]]
    get_config: Callable[[str], Awaitable[MemoryStoreConfig]]
    store_ref: Callable[[str, str], StoreRef]
    documents: MemoryDocumentRepo
    retrieval: KnowledgeRetrieval
    reconciler: MemoryReconciler
    audit: AuditService
    embedding_resolver: EmbeddingResolver


def collaborators_from_service(svc: MemoryService) -> OrganizerCollaborators:
    """Project a live ``MemoryService`` onto the organizer's collaborators."""
    return OrganizerCollaborators(
        resolve_store=svc.resolved_store,
        get_config=svc.get_store_config,
        store_ref=svc._recall.store_ref,
        documents=svc._documents,
        retrieval=svc._retrieval,
        reconciler=svc._reconciler,
        audit=svc._audit,
        embedding_resolver=svc._resolve_embedding,
    )
