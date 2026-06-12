"""Shared knowledge substrate domain (kind-agnostic).

Value objects + ports used by BOTH the ``knowledge_base`` and ``memory`` kinds.
This package is the only domain code those two kinds share; it is exempt from
the cross-kind import bans because it is the substrate itself.

Pure: stdlib + Pydantic only. No SQLAlchemy, no external engine SDKs.
"""

from __future__ import annotations

from coffer.domain.knowledge.converter import MarkdownConverter
from coffer.domain.knowledge.document import Document
from coffer.domain.knowledge.embedder import EmbeddingConfig, EmbeddingProvider
from coffer.domain.knowledge.index import KnowledgeIndex
from coffer.domain.knowledge.retrieval import (
    GrepHit,
    MemoryHit,
    Passage,
    RetrievalMode,
    SearchResult,
    StoreRef,
)

__all__ = [
    "Document",
    "EmbeddingConfig",
    "EmbeddingProvider",
    "GrepHit",
    "KnowledgeIndex",
    "MarkdownConverter",
    "MemoryHit",
    "Passage",
    "RetrievalMode",
    "SearchResult",
    "StoreRef",
]
