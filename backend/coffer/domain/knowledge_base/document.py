"""KB-face view of the unified ``Document`` entity (spec 006 redesign).

The KB and memory kinds share one ``Document`` (``domain/knowledge``); this
module re-exports it under the KB path.
"""

from __future__ import annotations

from coffer.domain.knowledge.document import KIND_KNOWLEDGE_BASE, Document

__all__ = ["KIND_KNOWLEDGE_BASE", "Document"]
