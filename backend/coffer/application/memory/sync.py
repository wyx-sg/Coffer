"""Lazy reindex-on-read reconcile for the memory face.

``recall`` (and every write) reconciles the index with the source-of-truth fact
files before searching: scan the (small) store dir for deltas by
``content_sha256``, then re-index changed/added facts and drop removed ones.
This is what makes out-of-band edits — including Claude's symlink edits —
visible immediately with no filesystem watcher.

Pure orchestration over the injected repo + index + reindexer; the per-fact file
read/scan is delegated to ``infrastructure.memory.files``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from coffer.application.knowledge.locks import StoreLocks
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.application.memory.ports import MemoryDocumentRepo
from coffer.domain.knowledge.document import (
    DOCUMENT_SCAN_LIMIT,
    KIND_MEMORY,
    Document,
)
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.memory.fact import MemoryFact
from coffer.infrastructure.knowledge.chunking import chunk_markdown
from coffer.infrastructure.memory.files import (
    FactFile,
    legacy_root_facts,
    scan_store_dir,
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconcileStats:
    indexed: int
    removed: int
    unchanged: int


# Memory topic docs are chunked per passage (heading/structure-aware) so recall
# surfaces the relevant section, not the whole document. Size/overlap are fixed
# here (not a MemoryStoreConfig field) to avoid per-store schema churn; the
# window mirrors the KB default. A short single-passage fact still yields one
# chunk, so inbox items and recall-isolation are unaffected.
_MEMORY_CHUNK_SIZE = 512
_MEMORY_CHUNK_OVERLAP = 64


def _chunk_fact(markdown: str) -> list[str]:
    return chunk_markdown(
        markdown, chunk_size=_MEMORY_CHUNK_SIZE, chunk_overlap=_MEMORY_CHUNK_OVERLAP
    )


def fact_to_document(
    fact: MemoryFact,
    *,
    store: StoreRef,
    content_sha256: str,
    path: str,
    embed_pending: bool = False,
) -> Document:
    """Project a ``MemoryFact`` onto a unified ``documents`` row (kind=memory).

    ``path`` is the fact's canonical ``.md`` file (the source of truth), per the
    data-model — recall hits surface it as their ``source``. ``embed_pending``
    carries the degraded-embed retry state (KB8) so a degraded fact is retried on
    the next reconcile."""
    metadata: dict[str, object] = {
        "type": fact.type,
        "actor": fact.actor,
        "origin_session_id": fact.origin_session_id,
    }
    return Document(
        id=fact.id,
        kind=KIND_MEMORY,
        resource_name=store.resource_name,
        project_id=store.project_id,
        path=path,
        title=fact.name,
        description=fact.description,
        content_sha256=content_sha256,
        embed_pending=embed_pending,
        source_mode="native",
        created_at=fact.created_at,
        updated_at=fact.updated_at,
        metadata=metadata,
    )


class MemoryReconciler:
    """Reconciles the memory index with the on-disk fact files for one store."""

    def __init__(
        self,
        *,
        documents: MemoryDocumentRepo,
        retrieval: KnowledgeRetrieval,
        reindexer: Reindexer,
    ) -> None:
        self._documents = documents
        self._retrieval = retrieval
        self._reindexer = reindexer
        self._locks = StoreLocks()

    def lock_for(self, store_name: str) -> asyncio.Lock:
        """The per-store lock guarding this reconciler's index mutations.

        Store teardown acquires it too, so a racing reconcile can't re-insert
        rows for a store being deleted."""
        return self._locks.lock(KIND_MEMORY, store_name)

    async def reconcile(
        self, *, store: StoreRef, embedding: EmbeddingConfig | None, force: bool = False
    ) -> ReconcileStats:
        """Reconcile the index with the on-disk fact files.

        ``force`` bypasses the ``content_sha256`` no-op gate so every fact is
        re-chunked/re-embedded — required when the store's retrieval/embedding
        config changes (the files are unchanged but the index is stale).
        """
        async with self._locks.lock(KIND_MEMORY, store.resource_name):
            return await self._reconcile_locked(store=store, embedding=embedding, force=force)

    async def _reconcile_locked(
        self, *, store: StoreRef, embedding: EmbeddingConfig | None, force: bool
    ) -> ReconcileStats:
        # The scan reads + parses every item in the knowledge/ lane — keep it
        # off the event loop.
        store_dir = Path(store.docs_dir)
        scan = await asyncio.to_thread(scan_store_dir, store_dir)
        on_disk = scan.files
        # FR-019: pre-lane facts at the store root are abandoned in place — note
        # them once so an operator can re-remember or seed them if wanted.
        legacy = await asyncio.to_thread(legacy_root_facts, store_dir)
        if legacy:
            _logger.info(
                "memory.legacy_root_facts_abandoned",
                extra={"store": store.resource_name, "count": len(legacy)},
            )
        known = {
            d.id: d
            for d in await self._documents.list_documents(
                KIND_MEMORY, store.resource_name, limit=DOCUMENT_SCAN_LIMIT, offset=0
            )
        }
        index = self._retrieval.index_for(
            store, dimensions=embedding.dimensions if embedding else None
        )
        indexed = unchanged = removed = 0

        for fact_id, ff in on_disk.items():
            existing = known.get(fact_id)
            previous = None if force else (existing.content_sha256 if existing else None)
            # A still-pending fact (embed degraded last time) must NOT be skipped
            # by the no-op gate, else its embed never retries (KB8).
            if (
                not force
                and existing is not None
                and existing.content_sha256 == ff.content_sha256
                and not existing.embed_pending
            ):
                unchanged += 1
                continue
            outcome = await self._reindexer.reindex(
                index=index,
                markdown=ff.fact.body,
                previous_sha=previous,
                embedding=embedding,
                doc_id=fact_id,
                chunker=_chunk_fact,
                # The fact name is its title → embed-context only (KB5); FTS raw.
                title=ff.fact.name,
                previous_embed_pending=(existing.embed_pending if existing else False),
            )
            doc = fact_to_document(
                ff.fact,
                store=store,
                content_sha256=outcome.content_sha256,
                path=str(ff.path),
                embed_pending=outcome.embed_pending,
            )
            await self._documents.upsert_document(doc)
            indexed += 1

        for fact_id in set(known) - set(on_disk):
            await index.delete_chunks(fact_id)
            await self._documents.delete_document(KIND_MEMORY, store.resource_name, fact_id)
            removed += 1

        return ReconcileStats(indexed=indexed, removed=removed, unchanged=unchanged)

    async def index_one(
        self, *, store: StoreRef, fact_file: FactFile, embedding: EmbeddingConfig | None
    ) -> None:
        """Index/refresh a single fact (write paths call this after writing)."""
        async with self._locks.lock(KIND_MEMORY, store.resource_name):
            index = self._retrieval.index_for(
                store, dimensions=embedding.dimensions if embedding else None
            )
            existing = await self._documents.get_document(
                KIND_MEMORY, store.resource_name, fact_file.fact.id
            )
            outcome = await self._reindexer.reindex(
                index=index,
                markdown=fact_file.fact.body,
                previous_sha=existing.content_sha256 if existing else None,
                embedding=embedding,
                doc_id=fact_file.fact.id,
                chunker=_chunk_fact,
                # The fact name is its title → embed-context only (KB5); FTS raw.
                title=fact_file.fact.name,
                previous_embed_pending=(existing.embed_pending if existing else False),
            )
            doc = fact_to_document(
                fact_file.fact,
                store=store,
                content_sha256=outcome.content_sha256,
                path=str(fact_file.path),
                embed_pending=outcome.embed_pending,
            )
            await self._documents.upsert_document(doc)

    async def remove_one(self, *, store: StoreRef, fact_id: str) -> None:
        async with self._locks.lock(KIND_MEMORY, store.resource_name):
            index = self._retrieval.index_for(store, dimensions=None)
            await index.delete_chunks(fact_id)
            await self._documents.delete_document(KIND_MEMORY, store.resource_name, fact_id)


__all__ = [
    "MemoryDocumentRepo",
    "MemoryReconciler",
    "ReconcileStats",
    "fact_to_document",
]
