"""Application layer for the one ``knowledge`` resource kind.

One facade over three scopes (``global``, ``project-<ULID>``, and named
collections) and two kinds of material (entries an agent writes, documents it
ingests). The retrieval facade + reindex routine underneath serve both, so the
keyword↔vector fallback and the single idempotent re-index routine live in
exactly one place.
"""

from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.document_tools import register_document_builtin_tools
from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.knowledge.reindex import Reindexer, ReindexOutcome
from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.application.knowledge.scope import ScopeResolver
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.sync import KnowledgeReconciler

__all__ = [
    "KnowledgeReconciler",
    "KnowledgeRetrieval",
    "KnowledgeService",
    "ReindexOutcome",
    "Reindexer",
    "ScopeResolver",
    "make_knowledge_kind",
    "register_document_builtin_tools",
    "register_knowledge_builtin_tools",
]
