"""Domain types for the `knowledge_base` resource kind.

Pure layer: imports stdlib + Pydantic only. No infrastructure, no SDKs.
"""

from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.knowledge_base.document import Document
from coffer.domain.knowledge_base.store import KnowledgeBaseStore, Passage

__all__ = ["Document", "KnowledgeBaseConfig", "KnowledgeBaseStore", "Passage"]
