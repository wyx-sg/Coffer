"""The single idempotent re-index routine, shared by both faces.

Every write path (KB ingest / edit / reindex-scan, memory remember / update /
lazy-recall scan) funnels a markdown body through :meth:`Reindexer.reindex`:

    compute content_sha256
     ├ unchanged + not embed-pending → true no-op (skip)
     ├ unchanged + embed-pending     → retry JUST the embed (re-chunk in memory,
     │                                 embed, upsert ONLY the vectors — no FTS /
     │                                 chunk rewrite, so no churn)
     └ changed   → delete old chunks (FTS5 + vec)
                 → markdown-aware chunk
                 → if vector configured: embed → upsert vec
                 → upsert chunks + documents_fts
                 → upsert the documents row (bump updated_at)

``content_sha256`` ALWAYS carries the real body hash; the separate
``embed_pending`` flag tracks the degraded-embed retry state (KB8). That decouple
keeps the no-op gate honest: a degraded doc whose body is unchanged is no longer
re-chunked + re-FTS'd on every scan (which it was when the sha was overwritten
with an empty-string sentinel).

``embed_pending`` tracks ONLY "the embedding PROVIDER call failed
(``EngineUnavailable``)". It is orthogonal to sqlite-vec extension availability:
if the provider succeeds but the vec table is unavailable, ``embedded=True`` and
we are NOT pending (that degradation is handled at query time by
``SearchResponse.fallback``) — same parity as the existing ``embedded`` flag.

The routine is pure orchestration over injected ports — the chunker, the
embedder factory, the index, and the document repo — so it stays engine-free and
testable with fakes.

The document TITLE is prepended (``"{title}\n\n{chunk}"``) ONLY to the text that
gets EMBEDDED, restoring standalone topic context to a mid-document chunk so its
vector recall improves (KB5). The chunks written to FTS / the chunk rows — and
thus the returned ``Passage.text`` — stay RAW (no prefix); the title is already
surfaced separately via ``Passage.title``. ``content_sha256`` likewise stays the
hash of the raw body, so prepending the title triggers NO mass re-embed.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from coffer.application.knowledge.retrieval import EmbedderFactory
from coffer.domain.errors import EngineUnavailable
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.domain.knowledge.index import KnowledgeIndex

_logger = logging.getLogger(__name__)

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
    #: True when the embed degraded (provider unavailable) so the chunks are
    #: keyword-only and the next reindex must retry JUST the embed. Distinct from
    #: ``content_sha256`` (always the real body hash) — see the module docstring.
    embed_pending: bool = False


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
        title: str = "",
        previous_embed_pending: bool = False,
    ) -> ReindexOutcome:
        """Re-index ``doc_id``'s chunks from ``markdown``.

        ``chunker`` is supplied per call so each face/store uses its own chunk
        params (KB: markdown-aware windows; memory: one chunk per fact). The
        returned ``content_sha256`` is ALWAYS the real body hash; the separate
        ``embed_pending`` flag carries the degraded-embed retry state.

        ``title`` is prepended ONLY to the EMBEDDED text (topic context for
        standalone chunks, KB5); the chunks sent to FTS / stored as rows stay raw.

        Three paths (see the module docstring):

        - content unchanged AND not ``previous_embed_pending`` → true no-op
          (``changed=False``); the caller skips writing the documents row too.
        - content unchanged BUT ``previous_embed_pending`` → the chunks + FTS are
          already current, only the embed was missing. Re-chunk in memory
          (deterministic), retry the embed, and upsert ONLY the vectors — no FTS /
          chunk rewrite, so this carries NO churn.
        - content changed (or first index) → drop + rebuild chunks/FTS/vec.

        When ``embedding`` is set the chunks are embedded, degrading silently to
        keyword-only on ``EngineUnavailable`` (``embed_pending=True``) so an
        unreachable provider never blocks a write.
        """
        new_sha = content_sha256(markdown)
        content_unchanged = previous_sha is not None and new_sha == previous_sha

        if content_unchanged and not previous_embed_pending:
            return ReindexOutcome(
                changed=False,
                chunk_count=0,
                embedded=False,
                content_sha256=new_sha,
                embed_pending=False,
            )

        if content_unchanged and previous_embed_pending:
            # Content (chunks + FTS) already current — only the embed was missing.
            # Retry JUST the embed and upsert ONLY the vectors (no FTS / chunk
            # rewrite ⇒ no churn). Chunk positions are deterministic so the fresh
            # vectors align with the stored chunks.
            chunks = chunker(markdown)
            vectors, embedded = await self._maybe_embed(
                chunks, embedding, doc_id=doc_id, title=title
            )
            if embedded and vectors is not None:
                await index.upsert_vectors(doc_id, vectors)
            # Still pending only if an embed was requested (vector enabled) yet
            # degraded again. Vector disabled since the degrade ⇒ no longer pending.
            still_pending = embedding is not None and bool(chunks) and not embedded
            return ReindexOutcome(
                changed=False,
                chunk_count=len(chunks),
                embedded=embedded,
                content_sha256=new_sha,
                embed_pending=still_pending,
            )

        # Content changed (or first index): full re-chunk + FTS + embed.
        chunks = chunker(markdown)
        vectors, embedded = await self._maybe_embed(chunks, embedding, doc_id=doc_id, title=title)
        # ``chunks`` (raw) is what lands in FTS / the chunk rows; only the
        # title-prefixed copy inside ``_maybe_embed`` reaches the embedder.
        chunk_count = await index.upsert_chunks(doc_id, chunks, vectors)
        embed_pending = embedding is not None and bool(chunks) and not embedded
        return ReindexOutcome(
            changed=True,
            chunk_count=chunk_count,
            embedded=embedded,
            content_sha256=new_sha,
            embed_pending=embed_pending,
        )

    async def _maybe_embed(
        self,
        chunks: Sequence[str],
        embedding: EmbeddingConfig | None,
        *,
        doc_id: str,
        title: str = "",
    ) -> tuple[list[list[float]] | None, bool]:
        if embedding is None or not chunks:
            return None, False
        # Prepend the doc title as topic context ONLY in the EMBEDDED text (KB5):
        # a standalone mid-document chunk loses the subject, so the title restores
        # it for better vector recall. ``chunks`` itself is untouched, so FTS / the
        # chunk rows / the returned ``Passage.text`` stay raw (title comes back via
        # ``Passage.title``). Empty title ⇒ embed the raw chunk unchanged.
        to_embed = [f"{title}\n\n{c}" if title else c for c in chunks]
        try:
            embedder = self._embedder_factory(embedding)
            vectors = await embedder.embed(to_embed)
        except EngineUnavailable as exc:
            # Provider library/endpoint missing — index keyword-only. Vector
            # recall will fall back at read time; the write must not fail.
            # ``reindex`` records ``embed_pending=True`` (NOT an empty sha) so the
            # next reconcile retries JUST the embed — but an operator still
            # deserves a signal.
            _logger.warning(
                "knowledge.reindex.embed_degraded",
                extra={"doc_id": doc_id, "provider": embedding.provider, "error": str(exc)},
            )
            return None, False
        return vectors, True
