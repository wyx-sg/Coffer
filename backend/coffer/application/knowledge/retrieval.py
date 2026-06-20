"""The shared retrieval facade (``RetrievalPort``).

Composes the chunk index (FTS5 + optional sqlite-vec), the ripgrep wrapper, and
the document repo behind one port used by both the KB and memory faces. The
keyword↔vector decision — including the **vector→keyword fallback** when no
embedding provider is configured / available — lives here, so neither face
duplicates it.

Layering: application MAY import infrastructure. The concrete engines
(``SqliteKnowledgeIndex``, ``RipgrepGrep``, the embedder clients) are injected
as small factories by the composition root, so this module stays engine-free in
its own imports and the importlinter engine-confinement contract holds.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol, runtime_checkable

from coffer.domain.errors import EngineUnavailable
from coffer.domain.knowledge.embedder import Embedder, EmbeddingConfig
from coffer.domain.knowledge.index import GrepPort, KnowledgeIndex
from coffer.domain.knowledge.retrieval import (
    GrepResult,
    Passage,
    RetrievalMode,
    SearchResult,
    StoreRef,
)

#: Reciprocal Rank Fusion constant (the standard value): a passage's fused
#: score is ``Σ 1/(RRF_K + rank)`` over the lists it appears in.
RRF_K = 60


@runtime_checkable
class IndexFactory(Protocol):
    """Builds a chunk index bound to one ``(kind, resource_name)`` store.

    ``dimensions`` is supplied when vector mode is enabled so the factory can
    attach a ``VecIndex`` at the right width; ``None`` means keyword/grep only.
    """

    def __call__(
        self, kind: str, resource_name: str, *, dimensions: int | None
    ) -> KnowledgeIndex: ...


#: Resolves the CURRENT global embedding config (embedding is no longer
#: per-resource), or ``None`` when vector is globally disabled/unconfigured.
#: Read at index/recall time so a Settings change applies without a restart.
EmbeddingResolver = Callable[[], Awaitable["EmbeddingConfig | None"]]


async def no_embedding() -> EmbeddingConfig | None:
    """Default resolver: vector disabled (keyword-only)."""
    return None


@runtime_checkable
class EmbedderFactory(Protocol):
    """Builds an ``Embedder`` for an ``EmbeddingConfig`` (or raises
    ``EngineUnavailable`` if the provider library is missing)."""

    def __call__(self, config: EmbeddingConfig) -> Embedder: ...


@runtime_checkable
class _StoreDroppable(Protocol):
    """An index that can drop its per-store substrate (the sqlite-vec table).

    Declared here rather than on the domain ``KnowledgeIndex`` protocol because
    store-level teardown is a composition concern, not part of the read/write
    contract every caller depends on."""

    async def drop_store(self) -> None: ...


def _rrf_fuse(lists: list[Sequence[Passage]], *, top_k: int) -> list[Passage]:
    """Reciprocal Rank Fusion over ranked passage lists (ADR-012).

    For each passage, ``score = Σ_over_lists 1/(RRF_K + rank)`` where ``rank`` is
    its 0-based position in that list. Passages are deduped by chunk identity
    ``(document_id, position)`` — a passage in BOTH lists sums both
    contributions, so it outranks any single-list hit. The fused passage keeps
    the first-seen text/title (the chunk identity already pins the same chunk).
    Returns the ``top_k`` highest-scoring passages, ties broken by first
    appearance for a stable order.
    """
    scores: dict[tuple[str, int], float] = {}
    passages: dict[tuple[str, int], Passage] = {}
    order: dict[tuple[str, int], int] = {}
    seq = 0
    for ranked in lists:
        for rank, passage in enumerate(ranked):
            key = (passage.document_id, passage.position)
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            if key not in passages:
                passages[key] = passage
                order[key] = seq
                seq += 1
    ranked_keys = sorted(scores, key=lambda k: (-scores[k], order[k]))
    # Surface the fused RRF score on each returned passage so callers see why a
    # hit ranked where it did (Passage is frozen — rebuild with the new score).
    fused: list[Passage] = []
    for key in ranked_keys[:top_k]:
        base = passages[key]
        fused.append(
            Passage(
                document_id=base.document_id,
                title=base.title,
                text=base.text,
                score=scores[key],
                position=base.position,
            )
        )
    return fused


class KnowledgeRetrieval:
    """High-level retrieval facade shared by KB + memory.

    Construct one per process; ``search``/``grep`` take a :class:`StoreRef` so a
    single instance serves every store. The per-store embedding config is passed
    on each ``search`` call (vector mode only) rather than held on the facade,
    keeping it stateless and config changes effective immediately.
    """

    def __init__(
        self,
        *,
        index_factory: IndexFactory,
        grep: GrepPort,
        embedder_factory: EmbedderFactory,
    ) -> None:
        self._index_factory = index_factory
        self._grep = grep
        self._embedder_factory = embedder_factory

    def index_for(self, store: StoreRef, *, dimensions: int | None) -> KnowledgeIndex:
        """The chunk index for one store (used by the reindex routine too)."""
        return self._index_factory(store.kind, store.resource_name, dimensions=dimensions)

    async def drop_store(self, store: StoreRef, *, dimensions: int | None) -> None:
        """Drop a store's per-store substrate (the sqlite-vec table) on delete.

        Chunk/FTS rows go through ``delete_resource``; this reaches the
        sqlite-vec table, which lives outside the async session and would
        otherwise leak across a same-name re-create. A no-op for keyword/grep
        stores (no vec table) or indexes that don't support the teardown."""
        index = self.index_for(store, dimensions=dimensions)
        if isinstance(index, _StoreDroppable):
            await index.drop_store()

    async def search(
        self,
        store: StoreRef,
        query: str,
        *,
        mode: RetrievalMode,
        top_k: int,
        embedding: EmbeddingConfig | None = None,
    ) -> SearchResult:
        """Run ``query`` over ``store`` in ``mode``.

        ``grep`` is not a passage mode; callers route grep through :meth:`grep`.
        A ``vector`` or ``hybrid`` request with no usable embedding provider
        degrades to ``keyword`` and the result carries ``fallback="keyword"`` —
        it never raises ``EngineUnavailable`` to the caller. ``hybrid`` fuses the
        keyword + vector result lists by reciprocal rank fusion (ADR-012).
        """
        if mode == "grep":
            raise ValueError("grep is not a passage mode; call grep() instead")
        top_k = max(1, top_k)

        if mode == "hybrid":
            return await self._hybrid_search(store, query, top_k=top_k, embedding=embedding)
        if mode == "vector":
            return await self._vector_search(store, query, top_k=top_k, embedding=embedding)

        index = self.index_for(store, dimensions=None)
        passages = await index.keyword_search(store.resource_name, query, top_k)
        return SearchResult(mode="keyword", passages=tuple(passages), fallback=None)

    async def _vector_search(
        self,
        store: StoreRef,
        query: str,
        *,
        top_k: int,
        embedding: EmbeddingConfig | None,
    ) -> SearchResult:
        vectors = await self._embed_query(query, embedding)
        if vectors is None:
            return await self._fallback_to_keyword(store, query, top_k=top_k, requested="vector")

        index = self.index_for(store, dimensions=embedding.dimensions)  # type: ignore[union-attr]
        passages = await index.vector_search(store.resource_name, vectors, top_k)
        return SearchResult(mode="vector", passages=tuple(passages), fallback=None)

    async def _hybrid_search(
        self,
        store: StoreRef,
        query: str,
        *,
        top_k: int,
        embedding: EmbeddingConfig | None,
    ) -> SearchResult:
        """RRF fusion of keyword + vector results (ADR-012).

        When no usable embedding provider is available the vector half is empty,
        so hybrid degrades to keyword-only and FLAGS it (``fallback="keyword"``)
        — the same never-error degradation as ``vector`` (FR-012)."""
        vectors = await self._embed_query(query, embedding)
        if vectors is None:
            return await self._fallback_to_keyword(store, query, top_k=top_k, requested="hybrid")

        # Both halves run; fetch top_k from each so fusion has full lists to work
        # with. The vec index is attached at the embedding width.
        kw_index = self.index_for(store, dimensions=None)
        vec_index = self.index_for(store, dimensions=embedding.dimensions)  # type: ignore[union-attr]
        keyword_hits = await kw_index.keyword_search(store.resource_name, query, top_k)
        vector_hits = await vec_index.vector_search(store.resource_name, vectors, top_k)
        fused = _rrf_fuse([keyword_hits, vector_hits], top_k=top_k)
        return SearchResult(mode="hybrid", passages=tuple(fused), fallback=None)

    async def _embed_query(
        self, query: str, embedding: EmbeddingConfig | None
    ) -> list[float] | None:
        """Embed ``query`` once, or ``None`` when no usable provider is available
        (unconfigured, ``EngineUnavailable``, or an empty result) — the caller
        then degrades to the flagged keyword fallback."""
        if embedding is None:
            return None
        try:
            embedder = self._embedder_factory(embedding)
            vectors = await embedder.embed([query])
        except EngineUnavailable:
            return None
        if not vectors:
            return None
        return list(vectors[0])

    async def _fallback_to_keyword(
        self, store: StoreRef, query: str, *, top_k: int, requested: RetrievalMode
    ) -> SearchResult:
        index = self.index_for(store, dimensions=None)
        passages = await index.keyword_search(store.resource_name, query, top_k)
        # mode stays the requested ``vector``/``hybrid`` while ``fallback``
        # records the degrade — surfaces report both.
        return SearchResult(mode=requested, passages=tuple(passages), fallback="keyword")

    async def grep(self, store: StoreRef, pattern: str, *, max_matches: int = 200) -> GrepResult:
        """Ripgrep over the store's ``docs_dir`` (no index)."""
        return await self._grep.grep(store.docs_dir, pattern, max_matches=max_matches)
