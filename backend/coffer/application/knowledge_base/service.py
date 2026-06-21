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
from coffer.application.knowledge_base import source_tracking
from coffer.application.knowledge_base.pipeline import KBPipeline
from coffer.application.knowledge_base.pipeline_helpers import (
    DocumentRepoPort,
    KBPaths,
    SourceStatus,
    chunker_for,
    du_bytes,
    read_markdown_body,
    reconcile_on_read,
)
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    DocumentNotFound,
    KBNotFound,
    ReconversionBlocked,
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
        source_path: str | None = None,
    ) -> Document:
        """Ingest one uploaded file: size check → convert → clean → frontmatter →
        write ``docs/``+``raw/`` → reindex → audit. A re-upload is matched to an
        existing document by filename (ADR-028): identical bytes are a no-op, a
        changed file updates that document in place (``replace``).

        ``source_path`` is the external original's absolute path; it is recorded
        in ``metadata`` (enabling later source-update detection) only for
        path-based ingests (CLI / desktop picker). A web byte-upload or agent
        ``add_document`` MUST NOT pass it — an untrusted surface must never
        populate an arbitrary server path."""
        config = await self.get_kb_config(kb_name)
        doc, status = await self._pipeline.ingest(
            kb_name=kb_name,
            filename=filename,
            raw_bytes=raw_bytes,
            config=config,
            replace=replace,
            source_path=source_path,
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

    # ----- external-source tracking (FR-021..024; impl in source_tracking.py) -----

    async def check_sources(self, *, kb_name: str, actor: str) -> list[SourceStatus]:
        """Classify each path-tracked document by re-hashing its external
        original vs the stored ``source_sha256`` (``unchanged``/``changed``/
        ``missing``). Detect-only audits nothing; with ``auto_update_sources`` a
        changed non-edited document is refreshed in place. See
        :mod:`coffer.application.knowledge_base.source_tracking`."""
        return await source_tracking.check_sources(self, kb_name=kb_name, actor=actor)

    async def update_from_source(self, *, kb_name: str, document_id: str, actor: str) -> Document:
        """Re-ingest a document from its tracked external ``source_path`` in
        place (preserving the ULID id), reusing the ``replace=True`` path.
        Refused once hand-edited. See
        :mod:`coffer.application.knowledge_base.source_tracking`."""
        return await source_tracking.update_from_source(
            self, kb_name=kb_name, document_id=document_id, actor=actor
        )

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

    async def _reconcile_on_read(self, kb_name: str, config: KnowledgeBaseConfig) -> None:
        """Lazy reindex-on-read (FR-008a / FR-016): reconcile the on-disk
        markdown against the SQLite index before serving a read/search.

        Intentionally ``-> None``: ``documents_degraded`` is surfaced from the
        PERSISTED ``embed_pending`` flag (``metrics()`` → ``count_pending_embeds``)
        rather than the transient per-scan count, so it stays observable without
        plumbing the scan count through every read path (KB8).

        Out-of-band edits to ``docs/<doc-id>.md`` (no filesystem watcher) funnel
        through the SAME idempotent reindex routine (``content_sha256`` no-op gate
        + file-vanished pruning).

        An unchanged corpus is detected by a cheap stat-only fingerprint and
        skips the full O(N) read+parse scan entirely; an out-of-band edit / add /
        remove bumps the fingerprint and is reconciled on the next read."""
        await reconcile_on_read(
            self._pipeline.fingerprint_cache,
            kb_name,
            self._paths.docs_dir(kb_name),
            lambda: self._pipeline.reindex_scan(kb_name=kb_name, config=config),
        )

    async def list_documents(
        self, *, kb_name: str, limit: int, offset: int, q: str | None = None
    ) -> tuple[list[Document], int]:
        config = await self.get_kb_config(kb_name)
        await self._reconcile_on_read(kb_name, config)
        # ``q`` is a case-insensitive title substring filter applied server-side
        # BEFORE limit/offset, so ``total`` reflects the filtered count (FR-010a).
        docs = await self._documents.list_documents(
            KIND_KNOWLEDGE_BASE, kb_name, limit=limit, offset=offset, q=q
        )
        total = await self._documents.count_documents(KIND_KNOWLEDGE_BASE, kb_name, q=q)
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

        The in-app viewer is read-only; surfaces hand these to open-in-external-editor
        / reveal (desktop via the OS opener, web via the loopback daemon)."""
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
        # ``mode`` is INTERNAL: external surfaces always pass ``None``, which
        # resolves to the store's ``default_mode`` (hybrid when vector is
        # enabled, else keyword). Internal callers/tests may still pin a mode;
        # vector/hybrid degrade to keyword (flagged internally) when no embedder
        # is available rather than erroring.
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

    async def document_count(self, *, kb_name: str) -> int:
        """Cheap indexed document count for the list path (no ``du_bytes`` walk)."""
        return await self._documents.count_documents(KIND_KNOWLEDGE_BASE, kb_name)

    async def metrics(self, *, kb_name: str) -> dict[str, object]:
        config = await self.get_kb_config(kb_name)
        doc_count = await self._documents.count_documents(KIND_KNOWLEDGE_BASE, kb_name)
        chunk_count = await self._documents.count_chunks(KIND_KNOWLEDGE_BASE, kb_name)
        kb_dir = self._paths.kb_dir(kb_name)
        disk = await asyncio.to_thread(du_bytes, kb_dir) if kb_dir.exists() else 0
        degraded = await self._documents.count_pending_embeds(KIND_KNOWLEDGE_BASE, kb_name)
        return {
            "document_count": doc_count,
            "chunk_count": chunk_count,
            "documents_degraded": degraded,
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


__all__ = ["DocumentRepoPort", "KnowledgeBaseService", "SourceStatus", "chunker_for"]
