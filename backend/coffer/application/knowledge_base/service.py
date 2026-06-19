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

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
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
from coffer.domain.errors import (
    DocumentLocked,
    DocumentNotFound,
    KBNotFound,
    ReconversionBlocked,
    SearchModeInvalid,
)
from coffer.domain.knowledge.converter import MarkdownConverter
from coffer.domain.knowledge.document import KIND_KNOWLEDGE_BASE, Document
from coffer.domain.knowledge.retrieval import (
    GrepResult,
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
        embedding_resolver: EmbeddingResolver = no_embedding,
    ) -> None:
        self._resources = resource_service
        self._documents = documents
        self._retrieval = retrieval
        self._reindexer = reindexer
        self._audit = audit
        self._paths = paths
        self._resolve_embedding = embedding_resolver
        self._pipeline = KBPipeline(
            documents=documents,
            converters=converters,
            retrieval=retrieval,
            reindexer=reindexer,
            paths=paths,
            embedding_resolver=embedding_resolver,
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
        """Ingest one uploaded file: size check → convert → clean → frontmatter →
        write ``docs/``+``raw/`` → reindex → audit. A re-upload is matched to an
        existing document by filename (ADR-028): identical bytes are a no-op, a
        changed file updates that document in place (``replace``)."""
        config = await self.get_kb_config(kb_name)
        doc, status = await self._pipeline.ingest(
            kb_name=kb_name,
            filename=filename,
            raw_bytes=raw_bytes,
            config=config,
            replace=replace,
        )
        # A byte-identical re-upload is an idempotent no-op — nothing changed, so
        # nothing is audited (FR-007). A changed re-upload of an existing filename
        # is an UPDATE in the audit trail (FR-016), not a second ingest.
        if status == "unchanged":
            return doc
        event = (
            AuditEventType.KB_DOCUMENT_UPDATED
            if status == "updated"
            else AuditEventType.KB_DOCUMENT_INGESTED
        )
        await self._audit.record(
            event.value,
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
        self._ensure_unlocked(kb_name, doc)
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
        self._ensure_unlocked(kb_name, doc)
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
        self._ensure_unlocked(kb_name, doc)
        await self._pipeline.delete(kb_name=kb_name, doc=doc)
        await self._audit.record(
            AuditEventType.KB_DOCUMENT_DELETED.value,
            ref=ResourceRef(KIND_KNOWLEDGE_BASE, kb_name),
            actor=actor,
            details={"document_id": document_id, "title": doc.title},
        )

    async def set_document_lock(
        self, *, kb_name: str, document_id: str, locked: bool, actor: str
    ) -> Document:
        """Lock or unlock a document (ADR-028). A locked document refuses every
        mutation (edit / reconvert / re-upload replace / delete) until unlocked;
        lock/unlock itself is always allowed. Idempotent: setting the lock to its
        current value is a no-op (no audit)."""
        await self.get_kb_config(kb_name)
        doc = await self._require_document(kb_name, document_id)
        if doc.locked == locked:
            return doc
        # Persist through the pipeline so the flag lands in BOTH the row and the
        # on-disk frontmatter (files are truth — a files-only rebuild restores it).
        updated = await self._pipeline.set_lock(kb_name=kb_name, doc=doc, locked=locked)
        event = AuditEventType.KB_DOCUMENT_LOCKED if locked else AuditEventType.KB_DOCUMENT_UNLOCKED
        await self._audit.record(
            event.value,
            ref=ResourceRef(KIND_KNOWLEDGE_BASE, kb_name),
            actor=actor,
            details={"document_id": document_id},
        )
        return updated

    # ----- reads -----

    async def _reconcile_on_read(self, kb_name: str, config: KnowledgeBaseConfig) -> None:
        """Lazy reindex-on-read (FR-008a / FR-016): reconcile the on-disk
        markdown against the SQLite index before serving a read/search.

        The in-app viewer is read-only, so users edit ``docs/<doc-id>.md``
        directly in their external editor with no filesystem watcher. This
        mirrors the memory face's reconcile-before-recall: it funnels through
        the SAME idempotent reindex scan (``content_sha256`` no-op gate +
        file-vanished pruning), so an unchanged corpus is a cheap no-op."""
        await self._pipeline.reindex_scan(kb_name=kb_name, config=config)

    async def list_documents(
        self, *, kb_name: str, limit: int, offset: int
    ) -> tuple[list[Document], int]:
        config = await self.get_kb_config(kb_name)
        await self._reconcile_on_read(kb_name, config)
        docs = await self._documents.list_documents(
            KIND_KNOWLEDGE_BASE, kb_name, limit=limit, offset=offset
        )
        total = await self._documents.count_documents(KIND_KNOWLEDGE_BASE, kb_name)
        return docs, total

    async def get_document(self, *, kb_name: str, document_id: str) -> Document:
        config = await self.get_kb_config(kb_name)
        await self._reconcile_on_read(kb_name, config)
        return await self._require_document(kb_name, document_id)

    async def chunk_counts(self, *, kb_name: str) -> dict[str, int]:
        """Per-document chunk counts for the KB (the wire ``chunk_count``)."""
        return await self._documents.chunk_counts(KIND_KNOWLEDGE_BASE, kb_name)

    def doc_paths(self, *, kb_name: str, document_id: str) -> tuple[str, str]:
        """Absolute markdown path + its containing folder for a document.

        The in-app viewer is read-only; surfaces hand these to the desktop for
        open-in-external-editor / reveal / copy-path."""
        path = self._paths.doc_path(kb_name, document_id)
        return str(path), str(path.parent)

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
        # Lazy reindex-on-read: surface out-of-band edits before searching the
        # index (FR-008a). No-op when the corpus is unchanged.
        await self._reconcile_on_read(kb_name, config)
        # An explicit mode the store cannot serve is a caller error (400), never
        # a silent rewrite. ``vector`` is the one exception: it always reaches
        # the facade so the keyword fallback is FLAGGED per the spec.
        if mode == "grep":
            raise SearchModeInvalid("grep", "grep is served by the grep endpoint")
        if mode is not None and mode != "vector" and mode not in config.enabled_modes:
            raise SearchModeInvalid(mode, "mode is not enabled for this knowledge base")
        chosen = mode or config.default_mode
        # An implicit search on a store whose default_mode is grep serves the
        # passage engine's keyword mode (grep is not a passage mode).
        if chosen == "grep":
            chosen = "keyword"
        embedding = await self._resolve_embedding() if config.vector_enabled else None
        return await self._retrieval.search(
            self._store_ref(kb_name),
            query,
            mode=chosen,
            top_k=top_k,
            embedding=embedding,
        )

    async def grep(self, *, kb_name: str, pattern: str, max_matches: int = 200) -> GrepResult:
        config = await self.get_kb_config(kb_name)
        # Grep reads ``docs/`` live, so it already reflects out-of-band edits;
        # we still reconcile (cheap no-op when unchanged) so the documents table
        # stays consistent with the files on the search path (FR-008a).
        await self._reconcile_on_read(kb_name, config)
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

    def _ensure_unlocked(self, kb_name: str, doc: Document) -> None:
        """Refuse a mutation on a locked document (ADR-028 / FR-021)."""
        if doc.locked:
            raise DocumentLocked(kb_name, doc.id)


__all__ = ["DocumentRepoPort", "KnowledgeBaseService", "chunker_for"]
