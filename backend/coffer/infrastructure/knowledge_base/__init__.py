"""Infrastructure adapters for the knowledge_base kind (spec 006 redesign).

The KB face has no kind-specific infrastructure of its own anymore — the
converters, chunker, FTS5/sqlite-vec index, embeddings, grep, and the unified
``documents``/``chunks`` repo all live in the shared substrate
``coffer.infrastructure.knowledge``. This package re-exports the KB-facing path
helpers for callers that import the documented KB path.
"""

from __future__ import annotations

from coffer.infrastructure.knowledge.paths import (
    doc_path,
    docs_dir,
    kb_dir,
    knowledge_root,
    raw_dir,
    raw_path,
)

__all__ = [
    "doc_path",
    "docs_dir",
    "kb_dir",
    "knowledge_root",
    "raw_dir",
    "raw_path",
]
