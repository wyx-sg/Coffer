"""LlamaIndex adapter for the `KnowledgeBaseStore` port.

This is the ONLY file in coffer that imports `llama_index.*`. Contract 7
(import-linter) enforces it. Imports are LAZY (inside methods) so that the
module loads even when llama-index-core is not installed — only the methods
that actually need the library will raise `EngineUnavailable`.

Each KB gets its own `embed_model` and node parser, passed directly to its
`VectorStoreIndex`. We deliberately do NOT touch LlamaIndex's process-global
`Settings`: that singleton is shared across every KB, so mutating it would
make ingest/search results depend on which KB was opened last.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from coffer.domain.errors import EngineUnavailable
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.knowledge_base.document import Document
from coffer.domain.knowledge_base.store import KnowledgeBaseStore, Passage
from coffer.infrastructure.knowledge_base.paths import kb_index_dir, kb_raw_dir


class LlamaIndexKnowledgeBaseStore(KnowledgeBaseStore):
    """Per-process registry of one LlamaIndex VectorStoreIndex per KB."""

    def __init__(self) -> None:
        self._indices: dict[str, Any] = {}
        self._configs: dict[str, KnowledgeBaseConfig] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, kb_name: str) -> asyncio.Lock:
        lock = self._locks.get(kb_name)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[kb_name] = lock
        return lock

    async def open(self, kb_name: str, config: KnowledgeBaseConfig) -> None:
        if kb_name in self._indices:
            return
        try:
            # Engine library, no type stubs; may be absent in some envs.
            from llama_index.core import (
                StorageContext,
                VectorStoreIndex,
                load_index_from_storage,
            )
            from llama_index.core.node_parser import SentenceSplitter
        except ImportError as exc:
            raise EngineUnavailable("llama_index", str(exc)) from exc

        # Per-KB embedding model + node parser — never the global `Settings`.
        embed_model = await asyncio.to_thread(_make_embed_model, config.embedding_model)
        splitter = SentenceSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )

        kb_raw_dir(kb_name).mkdir(parents=True, exist_ok=True)
        idx_dir = kb_index_dir(kb_name)
        idx_dir.mkdir(parents=True, exist_ok=True)

        if any(idx_dir.iterdir()):
            storage = await asyncio.to_thread(
                StorageContext.from_defaults, persist_dir=str(idx_dir)
            )
            index = await asyncio.to_thread(
                load_index_from_storage,
                storage,
                embed_model=embed_model,
                transformations=[splitter],
            )
        else:
            storage = StorageContext.from_defaults()
            index = VectorStoreIndex(
                nodes=[],
                storage_context=storage,
                embed_model=embed_model,
                transformations=[splitter],
            )
            await asyncio.to_thread(index.storage_context.persist, str(idx_dir))

        self._indices[kb_name] = index
        self._configs[kb_name] = config

    async def ingest(self, kb_name: str, document: Document, text: str) -> int:
        index = self._indices.get(kb_name)
        if index is None:
            await self.open(kb_name, self._configs.get(kb_name) or _require_config(kb_name))
            index = self._indices[kb_name]

        from llama_index.core.schema import Document as LIDocument

        async with self._lock(kb_name):
            li_doc = LIDocument(
                text=text,
                doc_id=document.id,
                metadata={
                    "document_id": document.id,
                    "filename": document.filename,
                    "extension": document.extension,
                    "sha256": document.sha256,
                },
            )
            # `insert` parses + embeds + persists, using the index's own
            # embed_model + transformations (set at construction time).
            await asyncio.to_thread(index.insert, li_doc)
            await asyncio.to_thread(index.storage_context.persist, str(kb_index_dir(kb_name)))

            # Count nodes for this doc_id by inspecting the docstore.
            ds = index.docstore
            # `get_ref_doc_info` returns the RefDocInfo or None.
            ref_info = ds.get_ref_doc_info(document.id) if hasattr(ds, "get_ref_doc_info") else None
            if ref_info is not None and getattr(ref_info, "node_ids", None):
                return len(ref_info.node_ids)
            return 1

    async def delete_document(self, kb_name: str, document_id: str) -> None:
        index = self._indices.get(kb_name)
        if index is None:
            return
        async with self._lock(kb_name):
            await asyncio.to_thread(index.delete_ref_doc, document_id, True)
            await asyncio.to_thread(index.storage_context.persist, str(kb_index_dir(kb_name)))

    async def search(self, kb_name: str, query: str, top_k: int) -> Sequence[Passage]:
        index = self._indices.get(kb_name)
        if index is None:
            await self.open(kb_name, self._configs.get(kb_name) or _require_config(kb_name))
            index = self._indices[kb_name]

        retriever = index.as_retriever(similarity_top_k=top_k)
        nodes = await asyncio.to_thread(retriever.retrieve, query)
        hits: list[Passage] = []
        for i, n in enumerate(nodes):
            meta = getattr(n, "metadata", {}) or {}
            text = ""
            if hasattr(n, "get_content"):
                text = n.get_content()
            elif hasattr(n, "text"):
                text = n.text
            hits.append(
                Passage(
                    document_id=str(meta.get("document_id") or n.node_id),
                    filename=str(meta.get("filename") or ""),
                    text=text or "",
                    score=float(getattr(n, "score", 0.0) or 0.0),
                    position=i,
                )
            )
        return hits

    async def drop(self, kb_name: str) -> None:
        async with self._lock(kb_name):
            self._indices.pop(kb_name, None)
            self._configs.pop(kb_name, None)
        # Release the per-KB lock entry as well — otherwise repeated
        # create/drop cycles on the same name accumulate stale ``asyncio.Lock``
        # instances in ``_locks`` (CODE22-011).
        self._locks.pop(kb_name, None)
        # On-disk deletion is the caller's responsibility (service.cleanup_kb).

    async def close(self) -> None:
        self._indices.clear()
        self._configs.clear()
        self._locks.clear()


def _make_embed_model(model_id: str) -> Any:
    """Construct a HuggingFace embedding model. Heavy; runs in a thread."""
    try:
        from llama_index.embeddings.huggingface import (  # type: ignore[import-untyped]
            HuggingFaceEmbedding,
        )
    except ImportError as exc:
        raise EngineUnavailable(
            "llama_index.embeddings.huggingface",
            f"{exc}; install with `pip install llama-index-embeddings-huggingface`",
        ) from exc
    return HuggingFaceEmbedding(model_name=model_id)


def _require_config(kb_name: str) -> KnowledgeBaseConfig:
    raise EngineUnavailable(
        "llama_index",
        f"KB {kb_name!r} was not opened with a config before use",
    )
