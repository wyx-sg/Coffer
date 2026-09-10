"""The ingestion half of ``KnowledgeService`` — documents in any format.

A scope holds two kinds of material. Entries are written directly by an agent
or a person (``service.py``); documents are *ingested*: a file in any format is
normalized to Markdown on disk (the source of truth) and served back over the
same three retrieval modes. SQLite is a rebuildable index either way.

This is a mixin rather than its own service because there is one knowledge
facade, not two — it lives in its own module only so neither file runs past the
project's 400-line ceiling. ``KnowledgeService`` supplies every attribute
declared below. Knows nothing about MarkItDown / sqlite-vec / embedding SDKs.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from coffer.application.audit_service import AuditService
from coffer.application.knowledge import source_tracking
from coffer.application.knowledge.pipeline import IngestPipeline
from coffer.application.knowledge.pipeline_helpers import (
    KnowledgePaths,
    SourceStatus,
    chunker_for,
    read_markdown_body,
    reconcile_on_read,
)
from coffer.application.knowledge.ports import DocumentRepoPort
from coffer.application.knowledge.retrieval import EmbeddingResolver, KnowledgeRetrieval
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import DocumentNotFound, ReconversionBlocked
from coffer.domain.knowledge.document import KIND_KNOWLEDGE, LANE_DOCS, Document
from coffer.domain.knowledge.retrieval import (
    GrepResult,
    RetrievalMode,
    SearchResult,
    StoreRef,
)
from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.domain.resource import ResourceRef


class DocumentOps(ABC):
    """Ingest / edit / re-index / read the documents in one knowledge scope."""

    # Supplied by ``KnowledgeService.__init__``.
    _audit: AuditService
    _documents: DocumentRepoPort
    _paths: KnowledgePaths
    _pipeline: IngestPipeline
    _resolve_embedding: EmbeddingResolver
    _retrieval: KnowledgeRetrieval

    @abstractmethod
    async def get_config(self, scope_name: str) -> KnowledgeConfig:
        """Implemented by ``KnowledgeService``."""

    @abstractmethod
    def _store_ref(self, scope_name: str) -> StoreRef:
        """Implemented by ``KnowledgeService``."""

    # ----- document writes -----

    async def ingest_bytes(
        self,
        *,
        scope_name: str,
        filename: str,
        raw_bytes: bytes,
        actor: str,
        replace: bool = False,
        source_path: str | None = None,
    ) -> Document:
        """Ingest one uploaded file: size check → convert → clean → frontmatter →
        write ``docs/``+``.raw/`` → reindex. A re-upload is matched to an
        existing document by filename (spec knowledge FR-062): identical bytes are a no-op, a
        changed file updates that document in place (``replace``).

        ``source_path`` is the external original's absolute path; it is recorded
        in ``metadata`` (enabling later source-update detection) only for
        path-based ingests (CLI / desktop picker). A web byte-upload or agent
        ``add_document`` MUST NOT pass it — an untrusted surface must never
        populate an arbitrary server path."""
        config = await self.get_config(scope_name)
        doc, _status = await self._pipeline.ingest(
            scope_name=scope_name,
            filename=filename,
            raw_bytes=raw_bytes,
            config=config,
            replace=replace,
            source_path=source_path,
        )
        return doc

    async def edit_document(
        self, *, scope_name: str, document_id: str, new_markdown: str, actor: str
    ) -> Document:
        """Replace a document's markdown body → ``source_mode=edited`` → reindex."""
        config = await self.get_config(scope_name)
        doc = await self._require_document(scope_name, document_id)
        return await self._pipeline.edit(
            scope_name=scope_name, doc=doc, new_markdown=new_markdown, config=config
        )

    async def reindex_documents(
        self,
        *,
        scope_name: str,
        actor: str,
        config: KnowledgeConfig | None = None,
        force: bool = False,
    ) -> dict[str, int]:
        """Rescan ``docs/`` and re-index every changed file from the markdown
        (reconstructs all SQLite state from the files).

        ``config`` lets the ``on_update_config`` hook pass a not-yet-persisted
        config; with ``force`` the sha no-op gate is bypassed because the chunk
        params themselves changed."""
        effective = config or await self.get_config(scope_name)
        return await self._pipeline.reindex_scan(
            scope_name=scope_name, config=effective, force=force
        )

    async def reembed_document(self, *, scope_name: str, document_id: str) -> Document:
        """Retry the embedding for one document (async re-embed worker unit): clears
        ``embed_pending`` when the provider is reachable, else leaves it set."""
        config = await self.get_config(scope_name)
        doc = await self._require_document(scope_name, document_id)
        return await self._pipeline.reembed(scope_name=scope_name, doc=doc, config=config)

    async def reconvert_document(
        self, *, scope_name: str, document_id: str, actor: str
    ) -> Document:
        """Re-convert a document from its raw original (blocked once edited)."""
        config = await self.get_config(scope_name)
        doc = await self._require_document(scope_name, document_id)
        if doc.source_mode == "edited":
            raise ReconversionBlocked(scope_name, document_id)
        return await self._pipeline.reconvert(scope_name=scope_name, doc=doc, config=config)

    async def delete_document(self, *, scope_name: str, document_id: str, actor: str) -> None:
        await self.get_config(scope_name)
        doc = await self._require_document(scope_name, document_id)
        await self._pipeline.delete(scope_name=scope_name, doc=doc)
        await self._audit.record(
            AuditEventType.KB_DOCUMENT_DELETED.value,
            ref=ResourceRef(KIND_KNOWLEDGE, scope_name),
            actor=actor,
            details={"document_id": document_id, "title": doc.title},
        )

    # ----- external-source tracking (impl in source_tracking.py) -----

    async def check_sources(self, *, scope_name: str, actor: str) -> list[SourceStatus]:
        """Classify each path-tracked document by re-hashing its external
        original vs the stored ``source_sha256`` (``unchanged``/``changed``/
        ``missing``); with ``auto_update_sources`` a changed non-edited document
        is refreshed in place."""
        return await source_tracking.check_sources(self, scope_name=scope_name, actor=actor)

    async def update_from_source(
        self, *, scope_name: str, document_id: str, actor: str
    ) -> Document:
        """Re-ingest a document from its tracked external ``source_path`` in
        place (preserving the ULID id), reusing the ``replace=True`` path.
        Refused once hand-edited."""
        return await source_tracking.update_from_source(
            self, scope_name=scope_name, document_id=document_id, actor=actor
        )

    # ----- reads -----

    async def _reconcile_on_read(self, scope_name: str, config: KnowledgeConfig) -> None:
        """Lazy reindex-on-read: reconcile the on-disk markdown against the
        SQLite index before serving a read/search.

        Intentionally ``-> None``: ``documents_degraded`` is surfaced from the
        PERSISTED ``embed_pending`` flag (``metrics()`` → ``count_pending_embeds``)
        rather than the transient per-scan count, so it stays observable without
        plumbing the scan count through every read path.

        Out-of-band edits to ``docs/<doc-id>.md`` (no filesystem watcher) funnel
        through the SAME idempotent reindex routine (``content_sha256`` no-op gate
        + file-vanished pruning). An unchanged corpus is detected by a cheap
        stat-only fingerprint and skips the full O(N) read+parse scan entirely."""
        await reconcile_on_read(
            self._pipeline.fingerprint_cache,
            scope_name,
            self._paths.docs_dir(scope_name),
            lambda: self._pipeline.reindex_scan(scope_name=scope_name, config=config),
        )

    async def list_documents(
        self, *, scope_name: str, limit: int, offset: int, q: str | None = None
    ) -> tuple[list[Document], int]:
        config = await self.get_config(scope_name)
        await self._reconcile_on_read(scope_name, config)
        # ``q`` is a case-insensitive title substring filter applied server-side
        # BEFORE limit/offset, so ``total`` reflects the filtered count.
        docs = await self._documents.list_documents(
            KIND_KNOWLEDGE, scope_name, limit=limit, offset=offset, q=q, lane=LANE_DOCS
        )
        total = await self._documents.count_documents(
            KIND_KNOWLEDGE, scope_name, q=q, lane=LANE_DOCS
        )
        return docs, total

    async def get_document(self, *, scope_name: str, document_id: str) -> Document:
        config = await self.get_config(scope_name)
        await self._reconcile_on_read(scope_name, config)
        return await self._require_document(scope_name, document_id)

    async def chunk_counts(self, *, scope_name: str) -> dict[str, int]:
        """Per-document chunk counts for the scope (the wire ``chunk_count``)."""
        return await self._documents.chunk_counts(KIND_KNOWLEDGE, scope_name, lane=LANE_DOCS)

    def doc_paths(self, *, scope_name: str, document_id: str) -> tuple[str, str]:
        """Absolute markdown path + its containing folder for an INGESTED document.

        The in-app viewer is read-only; surfaces hand these to
        open-in-external-editor / reveal through the loopback daemon.

        Only valid for an id in the ``docs/`` lane: the path is derived as
        ``docs/<id>.md`` unconditionally, so calling it with a *note* id returns
        a path that does not exist (a note lives under ``notes/``). Callers that
        may hold either kind of id must test first —
        ``builtin_tools.is_document()`` does exactly that."""
        path = self._paths.doc_path(scope_name, document_id)
        return str(path), str(path.parent)

    async def read_document(self, *, scope_name: str, document_id: str) -> tuple[Document, str]:
        """Return the document row + its full markdown (frontmatter + body)."""
        doc = await self.get_document(scope_name=scope_name, document_id=document_id)
        path = self._paths.doc_path(scope_name, document_id)
        if not path.exists():
            raise DocumentNotFound(scope_name, document_id)
        text = await asyncio.to_thread(path.read_text, "utf-8")
        return doc, text

    async def get_document_text(self, *, scope_name: str, document_id: str) -> tuple[Document, str]:
        """The markdown body only (no frontmatter)."""
        doc, full = await self.read_document(scope_name=scope_name, document_id=document_id)
        return doc, read_markdown_body(full)

    async def search(
        self, *, scope_name: str, query: str, top_k: int = 5, mode: RetrievalMode | None = None
    ) -> SearchResult:
        config = await self.get_config(scope_name)
        # Lazy reindex-on-read: surface out-of-band edits before searching.
        await self._reconcile_on_read(scope_name, config)
        # ``mode`` is INTERNAL: external surfaces always pass ``None``, which
        # resolves to the scope's ``default_mode`` (hybrid when vector is
        # enabled, else keyword). Internal callers/tests may still pin a mode;
        # vector/hybrid degrade to keyword (flagged internally) when no embedder
        # is available rather than erroring.
        chosen = mode or config.default_mode
        # An implicit search on a scope whose default_mode is grep serves the
        # passage engine's keyword mode (grep is not a passage mode).
        if chosen == "grep":
            chosen = "keyword"
        embedding = await self._resolve_embedding() if config.vector_enabled else None
        return await self._retrieval.search(
            self._store_ref(scope_name), query, mode=chosen, top_k=top_k, embedding=embedding
        )

    async def grep(self, *, scope_name: str, pattern: str, max_matches: int = 200) -> GrepResult:
        config = await self.get_config(scope_name)
        # Grep reads the files live, so it already reflects out-of-band edits;
        # we still reconcile (cheap no-op when unchanged) so the documents table
        # stays consistent with the files on the search path.
        await self._reconcile_on_read(scope_name, config)
        return await self._retrieval.grep(
            self._store_ref(scope_name), pattern, max_matches=max_matches
        )

    async def document_count(self, *, scope_name: str) -> int:
        """Cheap indexed document count for the list path (no ``du_bytes`` walk)."""
        return await self._documents.count_documents(KIND_KNOWLEDGE, scope_name, lane=LANE_DOCS)

    # ----- internals -----

    async def _require_document(self, scope_name: str, document_id: str) -> Document:
        doc = await self._documents.get_document(KIND_KNOWLEDGE, scope_name, document_id)
        if doc is None:
            raise DocumentNotFound(scope_name, document_id)
        return doc


__all__ = ["DocumentOps", "DocumentRepoPort", "SourceStatus", "chunker_for"]
