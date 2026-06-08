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

import json
from dataclasses import dataclass
from pathlib import Path

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


def fact_to_document(fact: MemoryFact, *, store: StoreRef, content_sha256: str) -> Document:
    """Project a ``MemoryFact`` onto a unified ``documents`` row (kind=memory)."""
    metadata = {
        "type": fact.type,
        "actor": fact.actor,
        "origin_session_id": fact.origin_session_id,
    }
    return Document(
        id=fact.id,
        kind=KIND_MEMORY,
        resource_name=store.resource_name,
        project_id=store.project_id,
        path=str(store.docs_dir),
        title=fact.name,
        description=fact.description,
        content_sha256=content_sha256,
        source_mode="native",
        created_at=fact.created_at,
        updated_at=fact.updated_at,
        metadata=json.loads(json.dumps(metadata)),
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

    async def reconcile(
        self, *, store: StoreRef, embedding: EmbeddingConfig | None
    ) -> ReconcileStats:
        scan = scan_store_dir(Path(store.docs_dir))
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
            previous = existing.content_sha256 if existing else None
            if existing is not None and existing.content_sha256 == ff.content_sha256:
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
            doc = fact_to_document(ff.fact, store=store, content_sha256=outcome.content_sha256)
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
        doc = fact_to_document(fact_file.fact, store=store, content_sha256=outcome.content_sha256)
        await self._documents.upsert_document(doc)

    async def remove_one(self, *, store: StoreRef, fact_id: str) -> None:
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
