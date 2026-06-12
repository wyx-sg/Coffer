"""KB-face view of the unified ``Document`` entity (spec 006 redesign).

The KB and memory kinds share one ``Document`` (``domain/knowledge``); this
module re-exports it under the KB path and adds the KB doc-id helper.
"""

from __future__ import annotations

from coffer.domain.knowledge.document import KIND_KNOWLEDGE_BASE, Document

#: A KB doc id is the first 16 hex chars of the original file's ``source_sha256``
#: — content-addressed so the same file ingests to the same id and ``<id>.md``.
DOC_ID_LEN = 16


def kb_doc_id(source_sha256: str) -> str:
    """First 16 hex chars of the source sha256 = the KB doc id / ``<id>.md``."""
    return source_sha256[:DOC_ID_LEN]


__all__ = ["DOC_ID_LEN", "KIND_KNOWLEDGE_BASE", "Document", "kb_doc_id"]
