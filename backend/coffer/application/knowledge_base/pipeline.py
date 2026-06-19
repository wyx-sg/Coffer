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
    check_size,
    chunker_for,
    document_from_frontmatter,
    extension_of,
    list_md_files,
    mkparent_write,
    render_doc_markdown,
    safe_rmtree_kb,
    scope_docs_dirs,
    set_frontmatter_locked,
    title_of,
)
from coffer.application.knowledge_base.pipeline_trash import TrashRebuildMixin
from coffer.domain.errors import DocumentLocked, IngestRejected
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
from coffer.infrastructure.knowledge.ids import new_ulid


class KBPipeline(TrashRebuildMixin):
    """The KB write/reindex paths (soft-delete / restore / purge in the mixin)."""

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

    def _store_ref(self, kb_name: str, project_id: str = WORKSPACE_GLOBAL_PROJECT_ID) -> StoreRef:
        # The keyword/vector index is keyed by (kind, resource_name) and shared
        # across scopes; ``docs_dir`` is scope-specific and backs grep (ADR-030).
        return StoreRef(
            kind=KIND_KNOWLEDGE_BASE,
            resource_name=kb_name,
            project_id=project_id,
            docs_dir=str(self._paths.docs_dir(kb_name, project_id)),
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
        project_id: str = WORKSPACE_GLOBAL_PROJECT_ID,
    ) -> tuple[Document, str]:
        """Ingest one upload. Returns ``(document, status)`` where ``status`` is:

        - ``"ingested"`` — a brand-new document (new ULID id), audited INGEST;
        - ``"updated"``  — a changed re-upload of an existing filename, updated
          in place under the same id (``replace=true``), audited UPDATE;
        - ``"unchanged"`` — a byte-identical re-upload, an idempotent no-op (no
          write, no audit).

        Identity is a stable ULID decoupled from content (ADR-028): a re-upload
        is matched to an existing document by ``original_filename`` in scope, not
        by its bytes, so an updated source updates the same document in place.
        """
        check_size(raw_bytes, config)
        prepared = await self._prepare(filename, raw_bytes)
        async with self._lock(kb_name):
            existing = await self._documents.find_by_filename(
                KIND_KNOWLEDGE_BASE, kb_name, project_id, filename
            )
            doc_id = prepared.doc_id
            status = "ingested"
            created_at: datetime | None = None
            if existing is not None:
                if existing.locked:
                    raise DocumentLocked(kb_name, existing.id)
                if str(existing.metadata.get("source_sha256", "")) == prepared.source_sha256:
                    # Byte-identical re-upload → idempotent no-op (FR-007).
                    return existing, "unchanged"
                if not replace:
                    raise IngestRejected(
                        "duplicate",
                        f"a document named {filename!r} already exists; "
                        "pass replace=true to update it in place",
                    )
                # Changed source, same filename → update the SAME doc in place:
                # reuse the id, overwrite docs/+raw/ (keep only the latest
                # original), reset source_mode to converted.
                doc_id = existing.id
                status = "updated"
                created_at = existing.created_at
            now = datetime.now(tz=UTC)
            await self._write_files(kb_name, doc_id, prepared, raw_bytes, filename, project_id)
            doc = build_kb_document(
                kb_name=kb_name,
                doc_id=doc_id,
                prepared=prepared,
                filename=filename,
                source_mode="converted",
                created_at=created_at or now,
                updated_at=now,
                project_id=project_id,
            )
            # previous_sha=None forces the row upsert even when the markdown body
            # is unchanged, so the new source_sha256 provenance always lands.
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
            full = render_doc_markdown(doc, body, source_mode="edited")
            dp = self._paths.doc_path(kb_name, doc.id, doc.project_id)
            await asyncio.to_thread(dp.write_text, full, "utf-8")
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

    # ----- reconvert / restore (both rebuild docs/ from the kept raw original) -----

    async def reconvert(
        self, *, kb_name: str, doc: Document, config: KnowledgeBaseConfig
    ) -> Document:
        async with self._lock(kb_name):
            return await self._rebuild_from_raw(
                kb_name=kb_name, doc=doc, config=config, clear_deleted=False
            )

    # ----- reindex scan -----

    async def reindex_scan(
        self, *, kb_name: str, config: KnowledgeBaseConfig, force: bool = False
    ) -> dict[str, int]:
        reindexed = 0
        skipped = 0
        removed = 0
        degraded = 0
        async with self._lock(kb_name):
            on_disk_ids: set[str] = set()
            # Walk the global docs/ AND every projects/<ulid>/docs/ (ADR-030);
            # the file's scope dir tells a DB-loss rebuild which project it is.
            for project_id, scope_dir in scope_docs_dirs(self._paths, kb_name):
                if not scope_dir.exists():
                    continue
                paths: list[Path] = await asyncio.to_thread(list_md_files, scope_dir)
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
                        doc = document_from_frontmatter(kb_name, doc_id, frontmatter, project_id)
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
            # Files are truth in BOTH directions: LIVE rows whose markdown
            # vanished are pruned. ``list_documents`` defaults to live-only and
            # all scopes, so a soft-deleted tombstone (no docs/ file, kept raw/)
            # is excluded here and is never resurrected nor pruned (ADR-030).
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

    # ----- lock -----

    async def set_lock(self, *, kb_name: str, doc: Document, locked: bool) -> Document:
        """Persist a lock toggle under the per-store lock: flip the on-disk
        frontmatter ``locked`` key (survives a files-only rebuild — ADR-028)."""
        async with self._lock(kb_name):
            await asyncio.to_thread(
                set_frontmatter_locked,
                self._paths.doc_path(kb_name, doc.id, doc.project_id),
                locked,
            )
            updated = await self._documents.set_locked(KIND_KNOWLEDGE_BASE, kb_name, doc.id, locked)
            return updated or dc_replace(doc, locked=locked)

    # ----- cleanup (full KB drop — hard) -----

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
        await asyncio.to_thread(
            safe_rmtree_kb, self._paths.kb_dir(kb_name), self._paths.knowledge_root()
        )

    # ----- internals -----

    async def _prepare(self, filename: str, raw_bytes: bytes) -> Prepared:
        source_sha = hashlib.sha256(raw_bytes).hexdigest()
        ext = extension_of(filename)
        fmt = ext.lstrip(".") or filename.rsplit(".", 1)[-1].lower()
        markdown, meta = await self._converters.convert(raw_bytes, fmt)
        body = markdown.strip()
        title = title_of(body, filename)
        return Prepared(
            # Stable ULID, decoupled from content (ADR-028) — minted for a new
            # document; a re-upload reuses the matched document's existing id.
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
        project_id: str = WORKSPACE_GLOBAL_PROJECT_ID,
    ) -> None:
        raw_path = self._paths.raw_path(kb_name, doc_id, prepared.extension, project_id)
        doc_path = self._paths.doc_path(kb_name, doc_id, project_id)

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
                # A new / replaced document is always unlocked (a locked one
                # rejects replace); persisted so a files-only rebuild keeps it.
                "locked": False,
            },
            prepared.markdown,
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
