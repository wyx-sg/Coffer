"""Knowledge domain — one kind, three scopes.

Value objects + ports for the single ``knowledge`` resource kind. What used to
be two faces (``memory`` and ``knowledge_base``) over one substrate is now one:
the substrate types (``Document``, the retrieval/index/converter ports) sit
here alongside the scope value objects and the per-scope config.

Pure: stdlib + Pydantic only. No SQLAlchemy, no external engine SDKs.
"""

from __future__ import annotations

from coffer.domain.knowledge.converter import MarkdownConverter
from coffer.domain.knowledge.document import KIND_KNOWLEDGE, Document
from coffer.domain.knowledge.embedder import EmbeddingConfig, EmbeddingProvider
from coffer.domain.knowledge.entry import Actor, KnowledgeEntry
from coffer.domain.knowledge.index import KnowledgeIndex
from coffer.domain.knowledge.lane import Lane
from coffer.domain.knowledge.retrieval import (
    GrepHit,
    MemoryHit,
    Passage,
    RetrievalMode,
    SearchResult,
    StoreRef,
)
from coffer.domain.knowledge.scope import (
    GLOBAL_SCOPE_NAME,
    PROJECT_SCOPE_PREFIX,
    KnowledgeScope,
    ResolvedScope,
    project_scope_name,
    scope_kind_of,
)
from coffer.domain.knowledge.scope_config import KnowledgeConfig

__all__ = [
    "GLOBAL_SCOPE_NAME",
    "KIND_KNOWLEDGE",
    "PROJECT_SCOPE_PREFIX",
    "Actor",
    "Document",
    "EmbeddingConfig",
    "EmbeddingProvider",
    "GrepHit",
    "KnowledgeConfig",
    "KnowledgeEntry",
    "KnowledgeIndex",
    "KnowledgeScope",
    "Lane",
    "MarkdownConverter",
    "MemoryHit",
    "Passage",
    "ResolvedScope",
    "RetrievalMode",
    "SearchResult",
    "StoreRef",
    "project_scope_name",
    "scope_kind_of",
]
