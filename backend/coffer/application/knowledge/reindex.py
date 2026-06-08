"""The single idempotent re-index routine, shared by both faces.

Every write path (KB ingest / edit / reindex-scan, memory remember / update /
lazy-recall scan) funnels a markdown body through :meth:`Reindexer.reindex`:

    compute content_sha256
     ├ unchanged → no-op (skip)
     └ changed   → delete old chunks (FTS5 + vec)
                 → markdown-aware chunk
                 → if vector configured: embed → upsert vec
                 → upsert chunks + documents_fts
                 → upsert the documents row (bump updated_at)

The routine is pure orchestration over injected ports — the chunker, the
embedder factory, the index, and the document repo — so it stays engine-free and
testable with fakes.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from coffer.application.knowledge.retrieval import EmbedderFactory
from coffer.domain.errors import EngineUnavailable
from coffer.domain.knowledge.document import Document
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.domain.knowledge.index import KnowledgeIndex

#: Chunk a markdown body into ordered pieces. Matches
#: ``infrastructure.knowledge.chunking.chunk_markdown``'s signature.
Chunker = Callable[[str], list[str]]


@dataclass(frozen=True)
class ReindexOutcome:
    """Result of one reindex call."""

    changed: bool
    chunk_count: int
    embedded: bool
    content_sha256: str


def content_sha256(markdown: str) -> str:
    """Hash of the markdown body — the reindex no-op gate."""
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


class Reindexer:
    """Re-indexes one document from its markdown body, idempotently."""

    def __init__(self, *, embedder_factory: EmbedderFactory) -> None:
        self._embedder_factory = embedder_factory

    async def reindex(
        self,
        *,
        index: KnowledgeIndex,
        markdown: str,
        previous_sha: str | None,
        embedding: EmbeddingConfig | None,
        doc_id: str,
        chunker: Chunker,
    ) -> ReindexOutcome:
        """Re-index ``doc_id``'s chunks from ``markdown``.

        ``chunker`` is supplied per call so each face/store uses its own chunk
        params (KB: markdown-aware windows; memory: one chunk per fact). If
        ``content_sha256(markdown) == previous_sha`` the call is a no-op
        (``changed=False``) — the caller skips writing the documents row too.
        Otherwise old chunks are dropped and rebuilt; when ``embedding`` is set
        the chunks are embedded (degrading silently to keyword-only on
        ``EngineUnavailable`` so an unreachable provider never blocks a write).
        """
        new_sha = content_sha256(markdown)
        if previous_sha is not None and new_sha == previous_sha:
            return ReindexOutcome(
                changed=False, chunk_count=0, embedded=False, content_sha256=new_sha
            )

        chunks = chunker(markdown)
        vectors, embedded = await self._maybe_embed(chunks, embedding)
        chunk_count = await index.upsert_chunks(doc_id, chunks, vectors)
        return ReindexOutcome(
            changed=True,
            chunk_count=chunk_count,
            embedded=embedded,
            content_sha256=new_sha,
        )

    async def _maybe_embed(
        self, chunks: Sequence[str], embedding: EmbeddingConfig | None
    ) -> tuple[list[list[float]] | None, bool]:
        if embedding is None or not chunks:
            return None, False
        try:
            embedder = self._embedder_factory(embedding)
            vectors = await embedder.embed(list(chunks))
        except EngineUnavailable:
            # Provider library/endpoint missing — index keyword-only. Vector
            # recall will fall back at read time; the write must not fail.
            return None, False
        return vectors, True


def doc_with_sha(doc: Document, sha: str) -> Document:
    """A copy of ``doc`` with ``content_sha256`` replaced (frozen dataclass)."""
    from dataclasses import replace

    return replace(doc, content_sha256=sha)
