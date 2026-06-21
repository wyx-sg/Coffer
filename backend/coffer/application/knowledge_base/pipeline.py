"""The KB any-format→Markdown ingest/edit/reindex pipeline.

Extracted from ``service.py`` so the orchestration service stays thin. The
pipeline owns the multi-step write paths (ingest / edit / reconvert /
reindex_scan / delete / cleanup): any-format upload → Markdown on disk → index.
Filesystem work is offloaded to worker threads; index/embedding work goes
through the shared ``KnowledgeRetrieval`` + ``Reindexer``."""

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
    build_kb_document,
    check_upload_size,
    chunker_for,
    docs_fingerprint,
    document_from_frontmatter,
    extension_of,
    mkparent_write,
    render_doc_markdown,
    render_ingest_markdown,
    title_of,
)
from coffer.domain.errors import IngestRejected
from coffer.domain.knowledge.converter import MarkdownConverter
from coffer.domain.knowledge.document import (
    DOCUMENT_SCAN_LIMIT,
    KIND_KNOWLEDGE_BASE,
    WORKSPACE_GLOBAL_PROJECT_ID,
    Document,
)
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.fs import atomic_write_bytes, atomic_write_text
from coffer.infrastructure.knowledge.ids import new_ulid


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
        # Serializes write paths per KB so concurrent ingest/edit/reindex don't
        # interleave index batches or duplicate embeds.
        self._locks = StoreLocks()
        # Per-KB stat-only docs/ fingerprint: the reconcile-on-read short-circuit
        # skips the full scan when unchanged; set by ``reindex_scan``.
        self.fingerprint_cache: dict[str, str] = {}

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
        source_path: str | None = None,
    ) -> tuple[Document, str]:
        """Ingest one upload. Returns ``(document, status)`` where ``status`` is:

        - ``"ingested"`` — a brand-new document (new ULID id), audited INGEST;
        - ``"updated"``  — a changed re-upload of an existing filename, updated
          in place under the same id (``replace=true``), audited UPDATE;
        - ``"unchanged"`` — a byte-identical re-upload, an idempotent no-op.

        Identity is a stable ULID decoupled from content (ADR-028): a re-upload
        is matched to an existing document by ``original_filename`` in scope, not
        by its bytes, so an updated source updates the same document in place.
        """
        check_upload_size(raw_bytes, config)
        prepared = await self._prepare(filename, raw_bytes)
        async with self._lock(kb_name):
            existing = await self._documents.find_by_filename(
                KIND_KNOWLEDGE_BASE, kb_name, WORKSPACE_GLOBAL_PROJECT_ID, filename
            )
            doc_id = prepared.doc_id
            status = "ingested"
            created_at: datetime | None = None
            if existing is not None:
                if str(existing.metadata.get("source_sha256", "")) == prepared.source_sha256:
                    # Byte-identical re-upload → idempotent no-op (FR-007).
                    return existing, "unchanged"
                if not replace:
                    raise IngestRejected(
                        "duplicate",
                        f"a document named {filename!r} already exists; "
                        "pass replace=true to update it in place",
                    )
                # Changed source, same filename → update the SAME doc in place.
                doc_id = existing.id
                status = "updated"
                created_at = existing.created_at
            now = datetime.now(tz=UTC)
            doc_created_at = created_at or now  # first ingest: now; re-upload: preserved
            await self._write_files(
                kb_name,
                doc_id,
                prepared,
                raw_bytes,
                filename,
                created_at=doc_created_at,
                updated_at=now,
                source_path=source_path,
            )
            doc = build_kb_document(
                kb_name=kb_name,
                doc_id=doc_id,
                prepared=prepared,
                filename=filename,
                source_mode="converted",
                created_at=doc_created_at,
                updated_at=now,
                source_path=source_path,
            )
            # previous_sha=None forces the row upsert so new source_sha256 lands.
            await self._index_and_persist(
                kb_name, doc, prepared.markdown, config, previous_sha=None
            )
            stored = await self._documents.get_document(KIND_KNOWLEDGE_BASE, kb_name, doc.id)
            return stored or doc, status

    # ----- edit -----

    async def edit(
        self, *, kb_name: str, doc: Document, new_markdown: str, config: KnowledgeBaseConfig
    ) -> Document:
        body = new_markdown.strip()
        if not body:
            raise IngestRejected("empty", "edited markdown is empty")
        async with self._lock(kb_name):
            now = datetime.now(tz=UTC)
            full = render_doc_markdown(doc, body, source_mode="edited", updated_at=now)
            await asyncio.to_thread(atomic_write_text, self._paths.doc_path(kb_name, doc.id), full)
            edited = dc_replace(
                doc,
                source_mode="edited",
                updated_at=now,
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
            now = datetime.now(tz=UTC)
            full = render_doc_markdown(doc, body, source_mode="converted", updated_at=now)
            await asyncio.to_thread(atomic_write_text, self._paths.doc_path(kb_name, doc.id), full)
            reconv = dc_replace(
                doc,
                source_mode="converted",
                updated_at=now,
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
            # Snapshot the docs/ fingerprint BEFORE reading any file — caching the
            # PRE-read state keeps the short-circuit race-safe.
            start_fp = await asyncio.to_thread(docs_fingerprint, docs_dir)
            paths: list[Path] = []
            if docs_dir.exists():
                paths = await asyncio.to_thread(lambda: sorted(docs_dir.glob("*.md")))
            # One batched row lookup keyed by id (reused by the vanished-file prune).
            known = await self._documents.list_documents(
                KIND_KNOWLEDGE_BASE, kb_name, limit=DOCUMENT_SCAN_LIMIT, offset=0
            )
            rows_by_id = {d.id: d for d in known}
            on_disk_ids: set[str] = set()
            for path in paths:
                doc_id = path.stem
                on_disk_ids.add(doc_id)
                doc = rows_by_id.get(doc_id)
                frontmatter, body = split_frontmatter(
                    await asyncio.to_thread(path.read_text, "utf-8")
                )
                if doc is None:
                    # No row (DB loss): reconstruct from the file's frontmatter —
                    # files are truth for the documents table too (FR-008/SC-005).
                    # The mtime is the timestamp fallback for files predating the
                    # created_at/updated_at keys.
                    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                    doc = document_from_frontmatter(kb_name, doc_id, frontmatter, mtime=mtime)
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
            for stale in (d for d in known if d.id not in on_disk_ids):
                await index.delete_chunks(stale.id)
                await self._documents.delete_document(KIND_KNOWLEDGE_BASE, kb_name, stale.id)
                removed += 1
            # Cache the PRE-read snapshot; set LAST so a mid-scan raise caches nothing.
            self.fingerprint_cache[kb_name] = start_fp
        return {
            "reindexed": reindexed,
            "skipped": skipped,
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
        # session, so it would survive ``delete_resource`` and leak on re-create.
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

    async def _prepare(self, filename: str, raw_bytes: bytes) -> Prepared:
        source_sha = hashlib.sha256(raw_bytes).hexdigest()
        ext = extension_of(filename)
        fmt = ext.lstrip(".") or filename.rsplit(".", 1)[-1].lower()
        markdown, meta = await self._converters.convert(raw_bytes, fmt)
        body = markdown.strip()
        title = title_of(body, filename)
        return Prepared(
            # Stable ULID, decoupled from content (ADR-028); a re-upload reuses
            # the matched document's existing id.
            doc_id=new_ulid(),
            source_sha256=source_sha,
            extension=ext,
            markdown=body,
            title=title,
            conversion_engine=str(meta.get("conversion_engine", "unknown")),
        )

    async def _write_files(
        self,
        kb_name: str,
        doc_id: str,
        prepared: Prepared,
        raw_bytes: bytes,
        filename: str,
        *,
        created_at: datetime,
        updated_at: datetime,
        source_path: str | None = None,
    ) -> None:
        raw_path = self._paths.raw_path(kb_name, doc_id, prepared.extension)
        doc_path = self._paths.doc_path(kb_name, doc_id)
        await asyncio.to_thread(atomic_write_bytes, raw_path, raw_bytes)
        full = render_ingest_markdown(
            prepared,
            filename,
            created_at=created_at,
            updated_at=updated_at,
            source_path=source_path,
        )
        await asyncio.to_thread(mkparent_write, doc_path, full)

    async def _index_and_persist(
        self,
        kb_name: str,
        doc: Document,
        markdown: str,
        config: KnowledgeBaseConfig,
        *,
        previous_sha: str | None,
    ) -> tuple[bool, bool]:
        """Run the shared reindex routine + persist the row. Returns
        ``(changed, degraded)`` — ``degraded`` is ``embed_pending`` (provider
        unavailable → keyword-only, retried next scan)."""
        embedding = await self._resolve_embedding() if config.vector_enabled else None
        index = self._retrieval.index_for(
            self._store_ref(kb_name),
            dimensions=embedding.dimensions if embedding else None,
        )
        # Canonicalize the body so the on-disk round-trip hashes identically.
        outcome = await self._reindexer.reindex(
            index=index,
            markdown=markdown.strip(),
            previous_sha=previous_sha,
            embedding=embedding,
            doc_id=doc.id,
            chunker=chunker_for(config),
            title=doc.title,
            previous_embed_pending=doc.embed_pending,
        )
        # Persist when content changed OR the pending flag flipped (retry cleared
        # it / fresh degrade); a true no-op skips the row write to avoid churn.
        pending_changed = outcome.embed_pending != doc.embed_pending
        if not outcome.changed and previous_sha is not None and not pending_changed:
            return False, outcome.embed_pending
        await self._documents.upsert_document(
            dc_replace(
                doc, content_sha256=outcome.content_sha256, embed_pending=outcome.embed_pending
            )
        )
        return outcome.changed, outcome.embed_pending
