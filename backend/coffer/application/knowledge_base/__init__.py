"""Application services for the `knowledge_base` resource kind."""

from coffer.application.knowledge_base.kind import make_kb_kind
from coffer.application.knowledge_base.service import KnowledgeBaseService

__all__ = ["KnowledgeBaseService", "make_kb_kind"]
