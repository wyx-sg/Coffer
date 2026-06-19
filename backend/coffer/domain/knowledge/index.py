"""The ``KnowledgeIndex`` / ``RetrievalPort`` ports.

What Coffer needs from the keyword (FTS5) + vector (sqlite-vec) index, so the
concrete SQLite engine stays in ``infrastructure/knowledge/``. Grep is a
separate file-based port (no index).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from coffer.domain.knowledge.document import Document
from coffer.domain.knowledge.retrieval import (
    GrepResult,
    Passage,
    RetrievalMode,
    SearchResult,
    StoreRef,
)


@runtime_checkable
class KnowledgeIndex(Protocol):
    """Chunk-level keyword + vector index over the unified ``documents`` table.

    Implementations own ``chunks`` / ``documents_fts`` / ``vec_chunks`` writes.
    ``vectors`` is ``None`` when vector mode is disabled (keyword/grep only).
    """

    async def upsert_chunks(
        self,
        document_id: str,
        chunks: Sequence[str],
        vectors: Sequence[Sequence[float]] | None,
    ) -> int:
        """Replace a document's chunks (FTS5 + optional vec). Returns count."""
        ...

    async def delete_chunks(self, document_id: str) -> None:
        """Remove a document's chunk / FTS5 / vec rows."""
        ...

    async def keyword_search(
        self, resource_name: str, query: str, top_k: int, *, project_id: str | None = None
    ) -> Sequence[Passage]:
        """FTS5 MATCH ordered by ``bm25()``. ``project_id`` (when given) restricts
        to that document scope (ADR-030); ``None`` searches the whole store."""
        ...

    async def vector_search(
        self,
        resource_name: str,
        vector: Sequence[float],
        top_k: int,
        *,
        project_id: str | None = None,
    ) -> Sequence[Passage]:
        """sqlite-vec KNN over chunk embeddings, optionally restricted to a
        document scope (ADR-030)."""
        ...


@runtime_checkable
class GrepPort(Protocol):
    """Ripgrep over a store's ``docs/`` directory (no index)."""

    async def grep(self, docs_dir: str, pattern: str, *, max_matches: int = 200) -> GrepResult: ...


@runtime_checkable
class RetrievalPort(Protocol):
    """High-level retrieval facade used by the kind services.

    Wraps the index + grep + (lazy) reconcile so the application layer talks to
    one port. ``search`` returns a ``SearchResult`` carrying the fallback flag.
    """

    async def index_document(self, store: StoreRef, doc: Document) -> None: ...

    async def remove_document(self, store: StoreRef, doc_id: str) -> None: ...

    async def search(
        self, store: StoreRef, query: str, *, mode: RetrievalMode, top_k: int
    ) -> SearchResult: ...

    async def grep(
        self, store: StoreRef, pattern: str, *, max_matches: int = 200
    ) -> GrepResult: ...
