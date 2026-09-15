"""FastAPI dependency providers for the one ``knowledge`` kind.

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.dependencies``,
typed concretely. One directory service, plus literal search and document
ingestion over it.
"""

from __future__ import annotations

from coffer.application.knowledge.ingest import IngestService
from coffer.application.knowledge.search import SearchService
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


_search_service: SearchService | None = None


def set_search_service(svc: SearchService) -> None:
    """Called by the composition root once on startup."""
    global _search_service
    _search_service = svc


def get_search_service() -> SearchService:
    """FastAPI Depends() target."""
    if _search_service is None:
        raise RuntimeError("search service not initialised")
    return _search_service


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
