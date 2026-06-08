"""KnowledgeBaseService — orchestration for the ``knowledge_base`` kind.

The KB is one face of the shared knowledge substrate: users upload files in any
format, Coffer normalizes each to Markdown on disk (the source of truth), and
serves them back over three retrieval modes (grep / keyword / vector). SQLite is
a rebuildable index.

This service composes:
- the kind-agnostic ``ResourceService`` (KB-as-Resource lifecycle / config),
- the unified ``DocumentRepo`` (``documents`` rows),
- the ``ConverterRegistry`` (any-format → Markdown),
- the shared ``KnowledgeRetrieval`` facade + ``Reindexer`` (chunk/FTS5/vec),
- ``AuditService``, and the on-disk path layout.

The any-format→Markdown pipeline is decomposed into small helpers in
``pipeline.py`` so no method runs long. Knows nothing about MarkItDown /
sqlite-vec / embedding SDKs.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.application.knowledge_base.pipeline import KBPipeline
from coffer.application.knowledge_base.pipeline_helpers import (
    DocumentRepoPort,
    KBPaths,
    chunker_for,
    du_bytes,
    read_markdown_body,
)
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import DocumentNotFound, KBNotFound, ReconversionBlocked
from coffer.domain.knowledge.converter import MarkdownConverter
from coffer.domain.knowledge.document import KIND_KNOWLEDGE_BASE, Document
from coffer.domain.knowledge.retrieval import (
    GrepHit,
    RetrievalMode,
    SearchResult,
    StoreRef,
)
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.resource import ResourceRef


class KnowledgeBaseService:
    """Application service for KB operations."""

    def __init__(
        self,
        *,
        resource_service: ResourceService,
        documents: DocumentRepoPort,
        converters: MarkdownConverter,
        retrieval: KnowledgeRetrieval,
        reindexer: Reindexer,
        audit: AuditService,
        paths: KBPaths,
    ) -> None:
        self._resources = resource_service
        self._documents = documents
        self._retrieval = retrieval
        self._reindexer = reindexer
        self._audit = audit
        self._paths = paths
        self._pipeline = KBPipeline(
            documents=documents,
            converters=converters,
            retrieval=retrieval,
            reindexer=reindexer,
            paths=paths,
        )

    # ----- KB-level -----

    async def get_kb_config(self, kb_name: str) -> KnowledgeBaseConfig:
        ref = ResourceRef(kind=KIND_KNOWLEDGE_BASE, name=kb_name)
        try:
            resource = await self._resources.get(ref)
        except Exception as exc:  # ResourceNotFound → KBNotFound
            raise KBNotFound(kb_name) from exc
        return KnowledgeBaseConfig.model_validate(resource.config)

    def _store_ref(self, kb_name: str) -> StoreRef:
        return StoreRef(
            kind=KIND_KNOWLEDGE_BASE,
            resource_name=kb_name,
            project_id="00000000000000000000000000",
            docs_dir=str(self._paths.docs_dir(kb_name)),
        )

    # ----- document writes -----

    async def ingest_bytes(
        self,
        *,
        kb_name: str,
        filename: str,
        raw_bytes: bytes,
        actor: str,
        replace: bool = False,
    ) -> Document:
        """Ingest one uploaded file: size check → source dedup → convert →
        clean → frontmatter → write ``docs/``+``raw/`` → reindex → audit."""
        config = await self.get_kb_config(kb_name)
        doc = await self._pipeline.ingest(
            kb_name=kb_name,
            filename=filename,
            raw_bytes=raw_bytes,
            config=config,
            replace=replace,
        )
        await self._audit.record(
            AuditEventType.KB_DOCUMENT_INGESTED.value,
            ref=ResourceRef(KIND_KNOWLEDGE_BASE, kb_name),
            actor=actor,
            details={
                "document_id": doc.id,
                "filename": filename,
                "source_mode": doc.source_mode,
            },
        )
        return doc

    async def edit_document(
        self, *, kb_name: str, document_id: str, new_markdown: str, actor: str
    ) -> Document:
        """Replace a document's markdown body → ``source_mode=edited`` →
        reindex → audit ``KB_DOCUMENT_UPDATED``."""
        config = await self.get_kb_config(kb_name)
        doc = await self._require_document(kb_name, document_id)
        updated = await self._pipeline.edit(
            kb_name=kb_name, doc=doc, new_markdown=new_markdown, config=config
        )
        await self._audit.record(
            AuditEventType.KB_DOCUMENT_UPDATED.value,
            ref=ResourceRef(KIND_KNOWLEDGE_BASE, kb_name),
            actor=actor,
            details={"document_id": document_id, "source_mode": updated.source_mode},
        )
        return updated

    async def reindex(self, *, kb_name: str, actor: str) -> dict[str, int]:
        """Rescan ``docs/`` and re-index every changed file from the markdown
        (reconstructs all SQLite state from the files)."""
        config = await self.get_kb_config(kb_name)
        stats = await self._pipeline.reindex_scan(kb_name=kb_name, config=config)
        await self._audit.record(
            AuditEventType.KB_REINDEXED.value,
            ref=ResourceRef(KIND_KNOWLEDGE_BASE, kb_name),
            actor=actor,
            details=dict(stats),
        )
        return stats

    async def reindex_with_config(
        self, *, kb_name: str, config: KnowledgeBaseConfig, actor: str
    ) -> dict[str, int]:
        """Re-index the whole corpus with an explicit (possibly not-yet-persisted)
        config. Used by the ``on_update_config`` hook so a chunk/embedding change
        re-chunks/re-embeds every document. Forces a rebuild (ignores the sha
        no-op gate) because the chunk params themselves changed."""
        stats = await self._pipeline.reindex_scan(kb_name=kb_name, config=config, force=True)
        await self._audit.record(
            AuditEventType.KB_REINDEXED.value,
            ref=ResourceRef(KIND_KNOWLEDGE_BASE, kb_name),
            actor=actor,
            details=dict(stats),
        )
        return stats

    async def reconvert_document(self, *, kb_name: str, document_id: str, actor: str) -> Document:
        """Re-convert a document from its raw original (blocked once edited)."""
        config = await self.get_kb_config(kb_name)
        doc = await self._require_document(kb_name, document_id)
        if doc.source_mode == "edited":
            raise ReconversionBlocked(kb_name, document_id)
        updated = await self._pipeline.reconvert(kb_name=kb_name, doc=doc, config=config)
        await self._audit.record(
            AuditEventType.KB_DOCUMENT_UPDATED.value,
            ref=ResourceRef(KIND_KNOWLEDGE_BASE, kb_name),
            actor=actor,
            details={"document_id": document_id, "source_mode": updated.source_mode},
        )
        return updated

    async def delete_document(self, *, kb_name: str, document_id: str, actor: str) -> None:
        await self.get_kb_config(kb_name)
        doc = await self._require_document(kb_name, document_id)
        await self._pipeline.delete(kb_name=kb_name, doc=doc)
        await self._audit.record(
            AuditEventType.KB_DOCUMENT_DELETED.value,
            ref=ResourceRef(KIND_KNOWLEDGE_BASE, kb_name),
            actor=actor,
            details={"document_id": document_id, "title": doc.title},
        )

    # ----- reads -----

    async def list_documents(
        self, *, kb_name: str, limit: int, offset: int
    ) -> tuple[list[Document], int]:
        await self.get_kb_config(kb_name)
        docs = await self._documents.list_documents(
            KIND_KNOWLEDGE_BASE, kb_name, limit=limit, offset=offset
        )
        total = await self._documents.count_documents(KIND_KNOWLEDGE_BASE, kb_name)
        return docs, total

    async def get_document(self, *, kb_name: str, document_id: str) -> Document:
        await self.get_kb_config(kb_name)
        return await self._require_document(kb_name, document_id)

    async def read_document(self, *, kb_name: str, document_id: str) -> tuple[Document, str]:
        """Return the document row + its full markdown (frontmatter + body)."""
        doc = await self.get_document(kb_name=kb_name, document_id=document_id)
        path = self._paths.doc_path(kb_name, document_id)
        if not path.exists():
            raise DocumentNotFound(kb_name, document_id)
        text = await asyncio.to_thread(path.read_text, "utf-8")
        return doc, text

    async def get_document_text(self, *, kb_name: str, document_id: str) -> tuple[Document, str]:
        """The markdown body only (no frontmatter)."""
        doc, full = await self.read_document(kb_name=kb_name, document_id=document_id)
        return doc, read_markdown_body(full)

    async def search(
        self, *, kb_name: str, query: str, top_k: int = 5, mode: RetrievalMode | None = None
    ) -> SearchResult:
        config = await self.get_kb_config(kb_name)
        chosen = mode or config.default_mode
        # An explicit ``vector`` request always reaches the facade so it can flag
        # the keyword fallback when no embedding provider is configured (the spec
        # requires a flagged degrade, never a silent rewrite). Other modes that
        # are not enabled fall back to the configured default.
        if chosen != "vector" and chosen not in config.enabled_modes:
            chosen = config.default_mode
        # The facade only takes passage modes; ``grep`` is a separate surface.
        if chosen == "grep":
            chosen = "keyword"
        return await self._retrieval.search(
            self._store_ref(kb_name),
            query,
            mode=chosen,
            top_k=top_k,
            embedding=config.embedding if config.vector_enabled else None,
        )

    async def grep(
        self, *, kb_name: str, pattern: str, max_matches: int = 200
    ) -> Sequence[GrepHit]:
        await self.get_kb_config(kb_name)
        return await self._retrieval.grep(
            self._store_ref(kb_name), pattern, max_matches=max_matches
        )

    async def metrics(self, *, kb_name: str) -> dict[str, object]:
        config = await self.get_kb_config(kb_name)
        doc_count = await self._documents.count_documents(KIND_KNOWLEDGE_BASE, kb_name)
        chunk_count = await self._documents.count_chunks(KIND_KNOWLEDGE_BASE, kb_name)
        kb_dir = self._paths.kb_dir(kb_name)
        disk = await asyncio.to_thread(du_bytes, kb_dir) if kb_dir.exists() else 0
        return {
            "document_count": doc_count,
            "chunk_count": chunk_count,
            "disk_bytes": disk,
            "enabled_modes": list(config.enabled_modes),
        }

    # ----- on_delete kind hook -----

    async def cleanup_kb(self, kb_name: str) -> None:
        """Drop the KB's index rows + on-disk dir (defense-in-depth rmtree)."""
        await self._pipeline.cleanup(kb_name)

    # ----- internals -----

    async def _require_document(self, kb_name: str, document_id: str) -> Document:
        doc = await self._documents.get_document(KIND_KNOWLEDGE_BASE, kb_name, document_id)
        if doc is None:
            raise DocumentNotFound(kb_name, document_id)
        return doc


__all__ = ["DocumentRepoPort", "KnowledgeBaseService", "chunker_for"]
