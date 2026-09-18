"""Application layer for the one ``knowledge`` resource kind.

Two lanes of Markdown files: ``sources/``, which people write, and ``topics/``,
which the curation pass derives from them and an agent reads with its own
tools. There is no retrieval facade and no reindex routine to re-export,
because there is neither an index nor a retrieval tool (spec knowledge FR-001,
FR-033).
"""

from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService

__all__ = [
    "KIND_KNOWLEDGE",
    "KnowledgeService",
    "make_knowledge_kind",
    "register_knowledge_builtin_tools",
]
