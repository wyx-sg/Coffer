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
from dataclasses import dataclass
from pathlib import Path

from coffer.application.knowledge.locks import StoreLocks
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.domain.knowledge.document import KIND_MEMORY, Document
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.memory.fact import MemoryFact
from coffer.infrastructure.memory.files import FactFile, scan_store_dir


@dataclass(frozen=True)
class ReconcileStats:
    indexed: int
    removed: int
    unchanged: int


def _one_chunk(markdown: str) -> list[str]:
    """Memory indexes one chunk per fact (a fact is a single short passage)."""
    body = markdown.strip()
    return [body] if body else []


def fact_to_document(
    fact: MemoryFact, *, store: StoreRef, content_sha256: str, path: str
) -> Document:
    """Project a ``MemoryFact`` onto a unified ``documents`` row (kind=memory).

    ``path`` is the fact's canonical ``.md`` file (the source of truth), per the
    data-model — recall hits surface it as their ``source``."""
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
        # The scan reads + parses every fact file — keep it off the event loop.
        scan = await asyncio.to_thread(scan_store_dir, Path(store.docs_dir))
        on_disk = scan.files
        known = {
            d.id: d
            for d in await self._documents.list_documents(
                KIND_MEMORY, store.resource_name, limit=100_000, offset=0
            )
        }
        index = self._retrieval.index_for(
            store, dimensions=embedding.dimensions if embedding else None
        )
        indexed = unchanged = removed = 0

        for fact_id, ff in on_disk.items():
            existing = known.get(fact_id)
            previous = None if force else (existing.content_sha256 if existing else None)
            if not force and existing is not None and existing.content_sha256 == ff.content_sha256:
                unchanged += 1
                continue
            outcome = await self._reindexer.reindex(
                index=index,
                markdown=ff.fact.body,
                previous_sha=previous,
                embedding=embedding,
                doc_id=fact_id,
                chunker=_one_chunk,
            )
            doc = fact_to_document(
                ff.fact,
                store=store,
                content_sha256=outcome.content_sha256,
                path=str(ff.path),
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
                chunker=_one_chunk,
            )
            doc = fact_to_document(
                fact_file.fact,
                store=store,
                content_sha256=outcome.content_sha256,
                path=str(fact_file.path),
            )
            await self._documents.upsert_document(doc)

    async def remove_one(self, *, store: StoreRef, fact_id: str) -> None:
        async with self._locks.lock(KIND_MEMORY, store.resource_name):
            index = self._retrieval.index_for(store, dimensions=None)
            await index.delete_chunks(fact_id)
            await self._documents.delete_document(KIND_MEMORY, store.resource_name, fact_id)


# The repo port (structurally the substrate ``DocumentRepo``) lives in
# ``ports.py`` so both ``sync.py`` and ``service.py`` share one definition.
from coffer.application.memory.ports import MemoryDocumentRepo  # noqa: E402

__all__ = [
    "MemoryDocumentRepo",
    "MemoryReconciler",
    "ReconcileStats",
    "fact_to_document",
]
