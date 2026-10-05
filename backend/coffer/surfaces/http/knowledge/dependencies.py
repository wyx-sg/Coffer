"""FastAPI dependency providers for the one ``knowledge`` kind.

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.dependencies``,
typed concretely. Three services: the directory itself, document ingestion
over it, and its changes feed. There is no search service to provide — the layer keeps no
index and offers no retrieval, on this surface or any other (spec knowledge
"Expose no knowledge tool"), so the module that used to be wired here no longer exists.
"""

from __future__ import annotations

from coffer.application.knowledge.change_service import KnowledgeChangeService
from coffer.application.knowledge.ingest import IngestService
from coffer.application.knowledge.service import KnowledgeService

_knowledge_service: KnowledgeService | None = None


def set_knowledge_service(svc: KnowledgeService) -> None:
    """Called by the composition root once on startup."""
    global _knowledge_service
    _knowledge_service = svc


def get_knowledge_service() -> KnowledgeService:
    """FastAPI Depends() target."""
    if _knowledge_service is None:
        raise RuntimeError("knowledge service not initialised")
    return _knowledge_service


_ingest_service: IngestService | None = None


def set_ingest_service(svc: IngestService) -> None:
    """Called by the composition root once on startup."""
    global _ingest_service
    _ingest_service = svc


def get_ingest_service() -> IngestService:
    """FastAPI Depends() target."""
    if _ingest_service is None:
        raise RuntimeError("ingest service not initialised")
    return _ingest_service


_change_service: KnowledgeChangeService | None = None


def set_change_service(svc: KnowledgeChangeService) -> None:
    """Called by the composition root once on startup."""
    global _change_service
    _change_service = svc


def get_change_service() -> KnowledgeChangeService:
    """FastAPI Depends() target: the changes feed, undoing a delete and a
    collection's description (spec knowledge "Follow edits across collections in
    one feed")."""
    if _change_service is None:
        raise RuntimeError("knowledge change service not initialised")
    return _change_service
