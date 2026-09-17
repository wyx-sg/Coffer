"""FastAPI dependency providers for the one ``knowledge`` kind.

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.dependencies``,
typed concretely. Two services only: the directory itself, and document
ingestion over it. There is no search service to provide — the layer keeps no
index and offers no retrieval, on this surface or any other (spec knowledge
FR-033), so the module that used to be wired here no longer exists.
"""

from __future__ import annotations

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
