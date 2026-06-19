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

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from coffer.domain.errors import EngineUnavailable
from coffer.domain.knowledge.embedder import Embedder, EmbeddingConfig
from coffer.domain.knowledge.index import GrepPort, KnowledgeIndex
from coffer.domain.knowledge.retrieval import (
    GrepResult,
    RetrievalMode,
    SearchResult,
    StoreRef,
)


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
        A ``vector`` request with no usable embedding provider degrades to
        ``keyword`` and the result carries ``fallback="keyword"`` — it never
        raises ``EngineUnavailable`` to the caller.
        """
        if mode == "grep":
            raise ValueError("grep is not a passage mode; call grep() instead")
        top_k = max(1, top_k)

        if mode == "vector":
            return await self._vector_search(store, query, top_k=top_k, embedding=embedding)

        index = self.index_for(store, dimensions=None)
        # Pass the store's scope so KB project searches filter at the SQL layer
        # (ADR-030); for memory it's the store's own scope, so it's a no-op.
        passages = await index.keyword_search(
            store.resource_name, query, top_k, project_id=store.project_id
        )
        return SearchResult(mode="keyword", passages=tuple(passages), fallback=None)

    async def _vector_search(
        self,
        store: StoreRef,
        query: str,
        *,
        top_k: int,
        embedding: EmbeddingConfig | None,
    ) -> SearchResult:
        if embedding is None:
            return await self._fallback_to_keyword(store, query, top_k=top_k)
        try:
            embedder = self._embedder_factory(embedding)
            vectors = await embedder.embed([query])
        except EngineUnavailable:
            return await self._fallback_to_keyword(store, query, top_k=top_k)
        if not vectors:
            return await self._fallback_to_keyword(store, query, top_k=top_k)

        index = self.index_for(store, dimensions=embedding.dimensions)
        passages = await index.vector_search(
            store.resource_name, vectors[0], top_k, project_id=store.project_id
        )
        return SearchResult(mode="vector", passages=tuple(passages), fallback=None)

    async def _fallback_to_keyword(
        self, store: StoreRef, query: str, *, top_k: int
    ) -> SearchResult:
        index = self.index_for(store, dimensions=None)
        passages = await index.keyword_search(
            store.resource_name, query, top_k, project_id=store.project_id
        )
        # mode stays ``vector`` (what the caller requested) while ``fallback``
        # records the degrade — surfaces report both.
        return SearchResult(mode="vector", passages=tuple(passages), fallback="keyword")

    async def grep(self, store: StoreRef, pattern: str, *, max_matches: int = 200) -> GrepResult:
        """Ripgrep over the store's ``docs_dir`` (no index)."""
        return await self._grep.grep(store.docs_dir, pattern, max_matches=max_matches)
