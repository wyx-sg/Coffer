"""The KB any-format→Markdown ingest/edit/reindex pipeline.

Extracted from ``service.py`` so the orchestration service stays thin. The
pipeline owns the multi-step write paths (ingest / edit / reconvert /
reindex_scan / delete / cleanup): any-format upload → Markdown on disk → index.
Filesystem work is offloaded to worker threads; index/embedding work goes
through the shared ``KnowledgeRetrieval`` + ``Reindexer``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import shutil
from dataclasses import replace as dc_replace
from datetime import UTC, datetime
from pathlib import Path

from coffer.application.knowledge.locks import StoreLocks
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.knowledge_base.pipeline_helpers import (
    DocumentRepoPort,
    KBPaths,
    Prepared,
    chunker_for,
    document_from_frontmatter,
    extension_of,
    mkparent_write,
    title_of,
)
from coffer.domain.errors import IngestRejected
from coffer.domain.knowledge.converter import MarkdownConverter
from coffer.domain.knowledge.document import (
    KIND_KNOWLEDGE_BASE,
    WORKSPACE_GLOBAL_PROJECT_ID,
    Document,
)
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.infrastructure.knowledge.frontmatter import (
    render_frontmatter,
    split_frontmatter,
)


class KBPipeline:
    """The KB write/reindex paths."""

    def __init__(
        self,
        *,
        documents: DocumentRepoPort,
        converters: MarkdownConverter,
        retrieval: KnowledgeRetrieval,
        reindexer: Reindexer,
        paths: KBPaths,
        embedding_resolver: EmbeddingResolver = no_embedding,
    ) -> None:
        self._documents = documents
        self._converters = converters
        self._retrieval = retrieval
        self._reindexer = reindexer
        self._paths = paths
        self._resolve_embedding = embedding_resolver  # global embedding config
        # Serializes write paths per KB so concurrent ingest/edit/reindex on one
        # store don't interleave index batches or duplicate embeds.
        self._locks = StoreLocks()

    def _lock(self, kb_name: str) -> asyncio.Lock:
        return self._locks.lock(KIND_KNOWLEDGE_BASE, kb_name)

    def _store_ref(self, kb_name: str) -> StoreRef:
        return StoreRef(
            kind=KIND_KNOWLEDGE_BASE,
            resource_name=kb_name,
            project_id=WORKSPACE_GLOBAL_PROJECT_ID,
            docs_dir=str(self._paths.docs_dir(kb_name)),
        )

    # ----- ingest -----

    async def ingest(
        self,
        *,
        kb_name: str,
        filename: str,
        raw_bytes: bytes,
        config: KnowledgeBaseConfig,
        replace: bool,
    ) -> tuple[Document, bool]:
        """Ingest one upload. Returns ``(document, replaced)`` — ``replaced`` is
        True for a replace overwrite (audited as UPDATE, not a second INGEST)."""
        self._check_size(raw_bytes, config)
        prepared = await self._prepare(filename, raw_bytes)
        async with self._lock(kb_name):
            existed = await self._dedup_guard(kb_name, prepared.source_sha256, replace)
            await self._write_files(kb_name, prepared, raw_bytes, filename)
            now = datetime.now(tz=UTC)
            doc = self._build_document(
                kb_name=kb_name,
                prepared=prepared,
                filename=filename,
                source_mode="converted",
                created_at=now,
                updated_at=now,
            )
            await self._index_and_persist(
                kb_name, doc, prepared.markdown, config, previous_sha=None
            )
            stored = await self._documents.get_document(KIND_KNOWLEDGE_BASE, kb_name, doc.id)
            return stored or doc, existed

    # ----- edit -----

    async def edit(
        self, *, kb_name: str, doc: Document, new_markdown: str, config: KnowledgeBaseConfig
    ) -> Document:
        body = new_markdown.strip()
        if not body:
            raise IngestRejected("empty", "edited markdown is empty")
        async with self._lock(kb_name):
            full = self._render_doc_markdown(doc, body, source_mode="edited")
            await asyncio.to_thread(self._paths.doc_path(kb_name, doc.id).write_text, full, "utf-8")
            edited = dc_replace(
                doc,
                source_mode="edited",
                updated_at=datetime.now(tz=UTC),
                title=title_of(body, doc.title),
            )
            await self._index_and_persist(
                kb_name, edited, body, config, previous_sha=doc.content_sha256
            )
            stored = await self._documents.get_document(KIND_KNOWLEDGE_BASE, kb_name, doc.id)
            return stored or edited

    # ----- reconvert -----

    async def reconvert(
        self, *, kb_name: str, doc: Document, config: KnowledgeBaseConfig
    ) -> Document:
        raw_ext = extension_of(str(doc.metadata.get("original_filename", "")))
        raw_path = self._paths.raw_path(kb_name, doc.id, raw_ext)
        raw_bytes = await asyncio.to_thread(raw_path.read_bytes)
        fmt = raw_ext.lstrip(".") or str(doc.metadata.get("original_format", ""))
        markdown, _meta = await self._converters.convert(raw_bytes, fmt)
        body = markdown.strip()
        async with self._lock(kb_name):
            full = self._render_doc_markdown(doc, body, source_mode="converted")
            await asyncio.to_thread(self._paths.doc_path(kb_name, doc.id).write_text, full, "utf-8")
            reconv = dc_replace(
                doc,
                source_mode="converted",
                updated_at=datetime.now(tz=UTC),
                title=title_of(body, doc.title),
            )
            await self._index_and_persist(
                kb_name, reconv, body, config, previous_sha=doc.content_sha256
            )
            stored = await self._documents.get_document(KIND_KNOWLEDGE_BASE, kb_name, doc.id)
            return stored or reconv

    # ----- reindex scan -----

    async def reindex_scan(
        self, *, kb_name: str, config: KnowledgeBaseConfig, force: bool = False
    ) -> dict[str, int]:
        docs_dir = self._paths.docs_dir(kb_name)
        reindexed = 0
        skipped = 0
        removed = 0
        degraded = 0
        async with self._lock(kb_name):
            paths: list[Path] = []
            if docs_dir.exists():
                paths = await asyncio.to_thread(lambda: sorted(docs_dir.glob("*.md")))
            on_disk_ids: set[str] = set()
            for path in paths:
                doc_id = path.stem
                on_disk_ids.add(doc_id)
                doc = await self._documents.get_document(KIND_KNOWLEDGE_BASE, kb_name, doc_id)
                frontmatter, body = split_frontmatter(
                    await asyncio.to_thread(path.read_text, "utf-8")
                )
                if doc is None:
                    # No row (DB loss / restore-from-backup): reconstruct it
                    # from the file's frontmatter — files are the source of
                    # truth for the documents table too (FR-008/SC-005).
                    doc = document_from_frontmatter(kb_name, doc_id, frontmatter)
                # ``force`` bypasses the sha no-op gate (chunk params changed).
                previous = None if force else doc.content_sha256
                changed, was_degraded = await self._index_and_persist(
                    kb_name, doc, body, config, previous_sha=previous
                )
                if changed:
                    reindexed += 1
                else:
                    skipped += 1
                if was_degraded:
                    degraded += 1
            # Files are truth in BOTH directions: rows whose markdown vanished are pruned.
            index = self._retrieval.index_for(self._store_ref(kb_name), dimensions=None)
            known = await self._documents.list_documents(
                KIND_KNOWLEDGE_BASE, kb_name, limit=100_000, offset=0
            )
            for stale in (d for d in known if d.id not in on_disk_ids):
                await index.delete_chunks(stale.id)
                await self._documents.delete_document(KIND_KNOWLEDGE_BASE, kb_name, stale.id)
                removed += 1
        return {"reindexed": reindexed, "skipped": skipped} | {
            "removed": removed,
            "degraded": degraded,
        }

    # ----- delete / cleanup -----

    async def delete(self, *, kb_name: str, doc: Document) -> None:
        async with self._lock(kb_name):
            index = self._retrieval.index_for(self._store_ref(kb_name), dimensions=None)
            await index.delete_chunks(doc.id)
            await self._documents.delete_document(KIND_KNOWLEDGE_BASE, kb_name, doc.id)
            raw_ext = extension_of(str(doc.metadata.get("original_filename", "")))
            with contextlib.suppress(OSError, ValueError):
                await asyncio.to_thread(self._paths.doc_path(kb_name, doc.id).unlink, True)
            with contextlib.suppress(OSError, ValueError):
                await asyncio.to_thread(self._paths.raw_path(kb_name, doc.id, raw_ext).unlink, True)

    async def cleanup(self, kb_name: str) -> None:
        async with self._lock(kb_name):
            await self._cleanup_locked(kb_name)

    async def _cleanup_locked(self, kb_name: str) -> None:
        await self._documents.delete_resource(KIND_KNOWLEDGE_BASE, kb_name)
        # Drop the per-store sqlite-vec table too: it lives outside the async
        # session, so it would survive ``delete_resource`` and leak across a
        # same-name re-create. Maintenance mode — no embedding width needed.
        with contextlib.suppress(Exception):
            await self._retrieval.drop_store(self._store_ref(kb_name), dimensions=None)
        kb_dir = self._paths.kb_dir(kb_name)
        if not kb_dir.exists():
            return
        resolved = kb_dir.resolve()
        root = self._paths.knowledge_root().resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            return
        if resolved == root:
            return
        await asyncio.to_thread(shutil.rmtree, resolved, ignore_errors=True)

    # ----- internals -----

    def _check_size(self, raw_bytes: bytes, config: KnowledgeBaseConfig) -> None:
        if not raw_bytes:
            raise IngestRejected("empty", "uploaded file is empty")
        if len(raw_bytes) > config.max_document_bytes:
            raise IngestRejected(
                "too_large",
                f"file size {len(raw_bytes)} exceeds KB limit {config.max_document_bytes}",
            )

    async def _prepare(self, filename: str, raw_bytes: bytes) -> Prepared:
        source_sha = hashlib.sha256(raw_bytes).hexdigest()
        ext = extension_of(filename)
        fmt = ext.lstrip(".") or filename.rsplit(".", 1)[-1].lower()
        markdown, meta = await self._converters.convert(raw_bytes, fmt)
        body = markdown.strip()
        title = title_of(body, filename)
        return Prepared(
            doc_id=source_sha[:16],
            source_sha256=source_sha,
            extension=ext,
            markdown=body,
            title=title,
            conversion_engine=str(meta.get("conversion_engine", "unknown")),
        )

    async def _dedup_guard(self, kb_name: str, source_sha: str, replace: bool) -> bool:
        """Reject a duplicate source unless ``replace``; returns whether the
        source already existed (a replace overwrite)."""
        exists = await self._documents.exists_source(KIND_KNOWLEDGE_BASE, kb_name, source_sha)
        if exists and not replace:
            raise IngestRejected(
                "duplicate",
                "a document with the same source content already exists; pass replace=true",
            )
        return exists

    async def _write_files(
        self, kb_name: str, prepared: Prepared, raw_bytes: bytes, filename: str
    ) -> None:
        raw_path = self._paths.raw_path(kb_name, prepared.doc_id, prepared.extension)
        doc_path = self._paths.doc_path(kb_name, prepared.doc_id)

        def _write() -> None:
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(raw_bytes)

        await asyncio.to_thread(_write)
        full = render_frontmatter(
            {
                "title": prepared.title,
                "source_filename": filename,
                "source_format": prepared.extension.lstrip("."),
                "source_sha256": prepared.source_sha256,
                "converter": prepared.conversion_engine,
                "source_mode": "converted",
            },
            prepared.markdown,
        )
        await asyncio.to_thread(mkparent_write, doc_path, full)

    def _build_document(
        self,
        *,
        kb_name: str,
        prepared: Prepared,
        filename: str,
        source_mode: str,
        created_at: datetime,
        updated_at: datetime,
    ) -> Document:
        return Document(
            id=prepared.doc_id,
            kind=KIND_KNOWLEDGE_BASE,
            resource_name=kb_name,
            project_id=WORKSPACE_GLOBAL_PROJECT_ID,
            path=f"docs/{prepared.doc_id}.md",
            title=prepared.title,
            description=None,
            content_sha256="",  # set by the reindex routine
            source_mode=source_mode,
            created_at=created_at,
            updated_at=updated_at,
            metadata={
                "original_filename": filename,
                "original_format": prepared.extension.lstrip("."),
                "source_sha256": prepared.source_sha256,
                "converted_at": created_at.isoformat(),
                "conversion_engine": prepared.conversion_engine,
            },
        )

    async def _index_and_persist(
        self,
        kb_name: str,
        doc: Document,
        markdown: str,
        config: KnowledgeBaseConfig,
        *,
        previous_sha: str | None,
    ) -> tuple[bool, bool]:
        """Run the shared reindex routine + persist the row.

        Returns ``(changed, degraded)`` — ``changed`` is whether the content was
        (re)indexed; ``degraded`` is whether an embed was requested but the
        provider was unavailable (indexed keyword-only, retried next scan)."""
        embedding = await self._resolve_embedding() if config.vector_enabled else None
        index = self._retrieval.index_for(
            self._store_ref(kb_name),
            dimensions=embedding.dimensions if embedding else None,
        )
        # Canonicalize the body so the on-disk round-trip hashes identically to
        # the freshly-ingested body — otherwise reindex never reaches a no-op.
        outcome = await self._reindexer.reindex(
            index=index,
            markdown=markdown.strip(),
            previous_sha=previous_sha,
            embedding=embedding,
            doc_id=doc.id,
            chunker=chunker_for(config),
        )
        degraded = outcome.changed and outcome.content_sha256 == ""
        if not outcome.changed and previous_sha is not None:
            return False, degraded
        await self._documents.upsert_document(
            dc_replace(doc, content_sha256=outcome.content_sha256)
        )
        return True, degraded

    def _render_doc_markdown(self, doc: Document, body: str, *, source_mode: str) -> str:
        return render_frontmatter(
            {
                "title": title_of(body, doc.title),
                "source_filename": str(doc.metadata.get("original_filename", "")),
                "source_format": str(doc.metadata.get("original_format", "")),
                "source_sha256": str(doc.metadata.get("source_sha256", "")),
                "converter": str(doc.metadata.get("conversion_engine", "")),
                "source_mode": source_mode,
            },
            body,
        )
