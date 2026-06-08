"""Shared retrieval application layer for the knowledge substrate.

Both faces (the ``knowledge_base`` and ``memory`` kinds) drive their search,
grep, and (re)index through the one facade defined here, so the keyword↔vector
fallback and the single idempotent re-index routine live in exactly one place.
"""

from coffer.application.knowledge.reindex import Reindexer, ReindexOutcome
from coffer.application.knowledge.retrieval import KnowledgeRetrieval

__all__ = ["KnowledgeRetrieval", "ReindexOutcome", "Reindexer"]
