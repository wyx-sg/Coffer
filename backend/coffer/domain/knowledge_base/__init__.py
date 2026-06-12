"""Domain types for the `knowledge_base` resource kind (spec 006 redesign).

Pure layer: imports stdlib + Pydantic only. The retrieval/index/converter
ports and the unified ``Document`` live in the shared ``coffer.domain.knowledge``
substrate; this package holds only the KB-specific config + doc-id helper.
"""

from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.knowledge_base.document import Document, kb_doc_id

__all__ = ["Document", "KnowledgeBaseConfig", "kb_doc_id"]
