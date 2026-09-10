"""The any-format→Markdown ingest/edit/reindex pipeline for one scope.

Split out of the service so the orchestration stays thin. The pipeline owns the
multi-step write paths (ingest / edit / reconvert / reembed / reindex_scan /
delete / cleanup): any-format upload → Markdown in the scope's ``docs/`` →
index. Filesystem work runs on worker threads; index/embedding work goes
through the shared ``KnowledgeRetrieval`` + ``Reindexer``.

The scope's other lane, ``notes/``, belongs to ``sync.KnowledgeReconciler``,
not here. Both write ``documents`` rows under the same
``(kind, resource_name)``, so each prunes only the rows whose file lives in the
lane it just scanned — otherwise one scanner would delete the other's index."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace as dc_replace
from datetime import UTC, datetime
from pathlib import Path

from coffer.application.knowledge.ingest_files import prepare_upload, write_ingested_files
from coffer.application.knowledge.locks import StoreLocks
from coffer.application.knowledge.pipeline_helpers import (
    KnowledgePaths,
    build_ingested_document,
    check_upload_size,
    chunker_for,
    docs_fingerprint,
    document_from_frontmatter,
    extension_of,
    render_doc_markdown,
    rmtree_scope_dir,
    title_of,
)
from coffer.application.knowledge.ports import DocumentRepoPort
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.knowledge.stores import in_lane, store_ref_for
from coffer.domain.errors import IngestRejected
from coffer.domain.knowledge.converter import MarkdownConverter
from coffer.domain.knowledge.document import DOCUMENT_SCAN_LIMIT, KIND_KNOWLEDGE, Document
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.fs import atomic_write_text


def _in_lane(path: str, lane: Path) -> bool:
    """Whether an indexed document's file belongs to the lane just scanned."""
    try:
        return Path(path).is_relative_to(lane)
    except (OSError, ValueError):
        return False


class IngestPipeline:
    """The KB write/reindex paths."""

    def __init__(
        self,
        *,
        documents: DocumentRepoPort,
        converters: MarkdownConverter,
        retrieval: KnowledgeRetrieval,
        reindexer: Reindexer,
        paths: KnowledgePaths,
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

    def _lock(self, scope_name: str) -> asyncio.Lock:
        return self._locks.lock(KIND_KNOWLEDGE, scope_name)

    def _store_ref(self, scope_name: str) -> StoreRef:
        return store_ref_for(scope_name, scope_dir=self._paths.scope_dir)

    # ----- ingest -----

    async def ingest(
        self,
        *,
        scope_name: str,
        filename: str,
        raw_bytes: bytes,
        config: KnowledgeConfig,
        replace: bool,
        source_path: str | None = None,
    ) -> tuple[Document, str]:
        """Ingest one upload. Returns ``(document, status)`` — ``"ingested"`` (new
        ULID id), ``"updated"`` (a changed re-upload of an existing filename, same
        id, ``replace=true``), or ``"unchanged"`` (a byte-identical re-upload, an
        idempotent no-op). Identity is a stable ULID decoupled from content
        (spec knowledge FR-062): a re-upload is matched by ``original_filename`` in
        scope, not by bytes."""
        check_upload_size(raw_bytes, config)
        prepared = await prepare_upload(self._converters, filename, raw_bytes)
        async with self._lock(scope_name):
            store = self._store_ref(scope_name)
            existing = await self._documents.find_by_filename(
                KIND_KNOWLEDGE, scope_name, store.project_id, filename
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
            doc_created_at = created_at or now  # first ingest: now; re-upload kept
            await write_ingested_files(
                self._paths,
                scope_name,
                doc_id,
                prepared,
                raw_bytes,
                filename,
                created_at=doc_created_at,
                updated_at=now,
                source_path=source_path,
            )
            doc = build_ingested_document(
                store=store,
                doc_id=doc_id,
                path=self._paths.doc_path(scope_name, doc_id),
                prepared=prepared,
                filename=filename,
                source_mode="converted",
                created_at=doc_created_at,
                updated_at=now,
                source_path=source_path,
            )
            # previous_sha=None forces the row upsert so new source_sha256 lands.
            await self._index_and_persist(
                scope_name, doc, prepared.markdown, config, previous_sha=None
            )
            stored = await self._documents.get_document(KIND_KNOWLEDGE, scope_name, doc.id)
            return stored or doc, status

    # ----- edit -----

    async def edit(
        self, *, scope_name: str, doc: Document, new_markdown: str, config: KnowledgeConfig
    ) -> Document:
        body = new_markdown.strip()
        if not body:
            raise IngestRejected("empty", "edited markdown is empty")
        async with self._lock(scope_name):
            now = datetime.now(tz=UTC)
            full = render_doc_markdown(doc, body, source_mode="edited", updated_at=now)
            await asyncio.to_thread(
                atomic_write_text, self._paths.doc_path(scope_name, doc.id), full
            )
            edited = dc_replace(
                doc, source_mode="edited", updated_at=now, title=title_of(body, doc.title)
            )
            await self._index_and_persist(
                scope_name, edited, body, config, previous_sha=doc.content_sha256
            )
            stored = await self._documents.get_document(KIND_KNOWLEDGE, scope_name, doc.id)
            return stored or edited

    # ----- reconvert -----

    async def reconvert(
        self, *, scope_name: str, doc: Document, config: KnowledgeConfig
    ) -> Document:
        raw_ext = extension_of(str(doc.metadata.get("original_filename", "")))
        raw_path = self._paths.raw_path(scope_name, doc.id, raw_ext)
        raw_bytes = await asyncio.to_thread(raw_path.read_bytes)
        fmt = raw_ext.lstrip(".") or str(doc.metadata.get("original_format", ""))
        markdown, _meta = await self._converters.convert(raw_bytes, fmt)
        body = markdown.strip()
        async with self._lock(scope_name):
            now = datetime.now(tz=UTC)
            full = render_doc_markdown(doc, body, source_mode="converted", updated_at=now)
            await asyncio.to_thread(
                atomic_write_text, self._paths.doc_path(scope_name, doc.id), full
            )
            reconv = dc_replace(
                doc, source_mode="converted", updated_at=now, title=title_of(body, doc.title)
            )
            await self._index_and_persist(
                scope_name, reconv, body, config, previous_sha=doc.content_sha256
            )
            stored = await self._documents.get_document(KIND_KNOWLEDGE, scope_name, doc.id)
            return stored or reconv

    async def reembed(self, *, scope_name: str, doc: Document, config: KnowledgeConfig) -> Document:
        """Retry JUST the embedding for one document (async re-embed path): re-run
        the shared reindex with the doc's CURRENT sha + ``embed_pending`` so only the
        vectors are upserted (no churn); a reachable provider clears the flag."""
        full = await asyncio.to_thread(self._paths.doc_path(scope_name, doc.id).read_text, "utf-8")
        _frontmatter, body = split_frontmatter(full)
        async with self._lock(scope_name):
            await self._index_and_persist(
                scope_name, doc, body, config, previous_sha=doc.content_sha256
            )
            stored = await self._documents.get_document(KIND_KNOWLEDGE, scope_name, doc.id)
            return stored or doc

    # ----- reindex scan -----

    async def reindex_scan(
        self, *, scope_name: str, config: KnowledgeConfig, force: bool = False
    ) -> dict[str, int]:
        docs_dir = self._paths.docs_dir(scope_name)
        reindexed = 0
        skipped = 0
        removed = 0
        degraded = 0
        async with self._lock(scope_name):
            # Snapshot the docs/ fingerprint BEFORE reading any file — caching the
            # PRE-read state keeps the short-circuit race-safe.
            start_fp = await asyncio.to_thread(docs_fingerprint, docs_dir)
            paths: list[Path] = []
            if docs_dir.exists():
                paths = await asyncio.to_thread(lambda: sorted(docs_dir.glob("*.md")))
            # One batched row lookup keyed by id (reused by the vanished-file
            # prune). Only rows whose file lives in THIS lane are ours: the
            # notes lane is reconciled separately into the same store.
            store = self._store_ref(scope_name)
            known = [
                d
                for d in await self._documents.list_documents(
                    KIND_KNOWLEDGE, scope_name, limit=DOCUMENT_SCAN_LIMIT, offset=0
                )
                if in_lane(d.path, docs_dir)
            ]
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
                    # files are truth for the documents table too (FR-008/SC-005);
                    # mtime is the timestamp fallback for files predating the keys.
                    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                    doc = document_from_frontmatter(
                        store, doc_id, frontmatter, path=path, mtime=mtime
                    )
                # ``force`` bypasses the sha no-op gate (chunk params changed).
                previous = None if force else doc.content_sha256
                changed, was_degraded = await self._index_and_persist(
                    scope_name, doc, body, config, previous_sha=previous
                )
                reindexed += 1 if changed else 0
                skipped += 0 if changed else 1
                degraded += 1 if was_degraded else 0
            # Files are truth in BOTH directions: rows whose markdown vanished are pruned.
            index = self._retrieval.index_for(store, dimensions=None)
            for stale in (d for d in known if d.id not in on_disk_ids):
                await index.delete_chunks(stale.id)
                await self._documents.delete_document(KIND_KNOWLEDGE, scope_name, stale.id)
                removed += 1
            # Cache the PRE-read snapshot; set LAST so a mid-scan raise caches nothing.
            self.fingerprint_cache[scope_name] = start_fp
        return {
            "reindexed": reindexed,
            "skipped": skipped,
            "removed": removed,
            "degraded": degraded,
        }

    # ----- delete / cleanup -----

    async def delete(self, *, scope_name: str, doc: Document) -> None:
        async with self._lock(scope_name):
            index = self._retrieval.index_for(self._store_ref(scope_name), dimensions=None)
            await index.delete_chunks(doc.id)
            await self._documents.delete_document(KIND_KNOWLEDGE, scope_name, doc.id)
            raw_ext = extension_of(str(doc.metadata.get("original_filename", "")))
            with contextlib.suppress(OSError, ValueError):
                await asyncio.to_thread(self._paths.doc_path(scope_name, doc.id).unlink, True)
            with contextlib.suppress(OSError, ValueError):
                await asyncio.to_thread(
                    self._paths.raw_path(scope_name, doc.id, raw_ext).unlink, True
                )

    async def cleanup(self, scope_name: str) -> None:
        async with self._lock(scope_name):
            await self._documents.delete_resource(KIND_KNOWLEDGE, scope_name)
            # Drop the per-scope sqlite-vec table too: it lives outside the
            # async session, so it survives ``delete_resource`` and would leak
            # across a same-name re-create.
            with contextlib.suppress(Exception):
                await self._retrieval.drop_store(self._store_ref(scope_name), dimensions=None)
            await rmtree_scope_dir(self._paths.scope_dir(scope_name), self._paths.knowledge_root())

    # ----- internals -----

    async def _index_and_persist(
        self,
        scope_name: str,
        doc: Document,
        markdown: str,
        config: KnowledgeConfig,
        *,
        previous_sha: str | None,
    ) -> tuple[bool, bool]:
        """Run the shared reindex routine + persist the row. Returns ``(changed,
        degraded)`` — ``degraded`` is ``embed_pending`` (provider unavailable →
        keyword-only, retried next scan)."""
        embedding = await self._resolve_embedding() if config.vector_enabled else None
        index = self._retrieval.index_for(
            self._store_ref(scope_name),
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
