"""Soft-delete / restore / purge + the shared reconvert-rebuild path.

Split out of ``pipeline.py`` to keep it under the file-size ceiling. Mixed into
``KBPipeline``; references the collaborators that class wires in ``__init__``.
See [ADR-030] (recoverable soft-delete / trash / restore) and [ADR-028] (the
rebuild-from-``raw/`` path shared by reconvert + restore).
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace as dc_replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coffer.application.knowledge_base.pipeline_helpers import (
    extension_of,
    mkparent_write,
    render_doc_markdown,
    title_of,
)
from coffer.domain.knowledge.document import KIND_KNOWLEDGE_BASE, Document
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig

if TYPE_CHECKING:
    from coffer.application.knowledge.retrieval import KnowledgeRetrieval
    from coffer.application.knowledge_base.pipeline_helpers import DocumentRepoPort, KBPaths
    from coffer.domain.knowledge.converter import MarkdownConverter
    from coffer.domain.knowledge.retrieval import StoreRef


class TrashRebuildMixin:
    """KB soft-delete / restore / purge + the reconvert-rebuild path.

    A behavior mixin for ``KBPipeline`` (which owns the collaborators declared
    below and the per-store lock); split here only for the file-size ceiling."""

    if TYPE_CHECKING:  # collaborators provided by KBPipeline.__init__
        _documents: DocumentRepoPort
        _retrieval: KnowledgeRetrieval
        _paths: KBPaths
        _converters: MarkdownConverter

        def _lock(self, kb_name: str) -> asyncio.Lock: ...
        def _store_ref(self, kb_name: str, project_id: str = ...) -> StoreRef: ...
        async def _index_and_persist(
            self,
            kb_name: str,
            doc: Document,
            markdown: str,
            config: KnowledgeBaseConfig,
            *,
            previous_sha: str | None,
        ) -> tuple[bool, bool]: ...

    async def soft_delete(self, *, kb_name: str, doc: Document) -> None:
        """Move a document to the trash (ADR-030): drop its ``docs/`` markdown +
        index chunks but KEEP the ``raw/`` original and the row (``deleted_at``
        set), so it can be restored. Memory keeps using a hard delete."""
        async with self._lock(kb_name):
            index = self._retrieval.index_for(self._store_ref(kb_name), dimensions=None)
            await index.delete_chunks(doc.id)
            await self._documents.soft_delete_document(KIND_KNOWLEDGE_BASE, kb_name, doc.id)
            with contextlib.suppress(OSError, ValueError):
                await asyncio.to_thread(
                    self._paths.doc_path(kb_name, doc.id, doc.project_id).unlink, True
                )

    async def purge(self, *, kb_name: str, doc: Document) -> None:
        """Permanently remove a trashed document: the row plus the kept ``raw/``
        original (its ``docs/`` markdown + index chunks were dropped at delete)."""
        async with self._lock(kb_name):
            index = self._retrieval.index_for(self._store_ref(kb_name), dimensions=None)
            await index.delete_chunks(doc.id)
            await self._documents.delete_document(KIND_KNOWLEDGE_BASE, kb_name, doc.id)
            raw_ext = extension_of(str(doc.metadata.get("original_filename", "")))
            with contextlib.suppress(OSError, ValueError):
                await asyncio.to_thread(
                    self._paths.doc_path(kb_name, doc.id, doc.project_id).unlink, True
                )
            with contextlib.suppress(OSError, ValueError):
                await asyncio.to_thread(
                    self._paths.raw_path(kb_name, doc.id, raw_ext, doc.project_id).unlink, True
                )

    async def restore(
        self, *, kb_name: str, doc: Document, config: KnowledgeBaseConfig
    ) -> Document:
        """Restore a soft-deleted document (ADR-030): re-convert from the kept
        ``raw/`` original, regenerate ``docs/``, re-index, and clear the
        tombstone. Body edits made before deletion are not recovered."""
        async with self._lock(kb_name):
            return await self._rebuild_from_raw(
                kb_name=kb_name, doc=doc, config=config, clear_deleted=True
            )

    async def _rebuild_from_raw(
        self, *, kb_name: str, doc: Document, config: KnowledgeBaseConfig, clear_deleted: bool
    ) -> Document:
        """Shared body of reconvert + restore: read ``raw/``, convert, rewrite
        ``docs/``, re-index. ``clear_deleted`` clears ``deleted_at`` (restore)
        and forces a full re-index (the tombstone dropped its chunks)."""
        pid = doc.project_id
        raw_ext = extension_of(str(doc.metadata.get("original_filename", "")))
        raw_path = self._paths.raw_path(kb_name, doc.id, raw_ext, pid)
        raw_bytes = await asyncio.to_thread(raw_path.read_bytes)
        fmt = raw_ext.lstrip(".") or str(doc.metadata.get("original_format", ""))
        markdown, _meta = await self._converters.convert(raw_bytes, fmt)
        body = markdown.strip()
        full = render_doc_markdown(doc, body, source_mode="converted")
        await asyncio.to_thread(mkparent_write, self._paths.doc_path(kb_name, doc.id, pid), full)
        rebuilt = dc_replace(
            doc,
            source_mode="converted",
            updated_at=datetime.now(tz=UTC),
            title=title_of(body, doc.title),
            deleted_at=None if clear_deleted else doc.deleted_at,
        )
        await self._index_and_persist(
            kb_name,
            rebuilt,
            body,
            config,
            previous_sha=None if clear_deleted else doc.content_sha256,
        )
        stored = await self._documents.get_document(KIND_KNOWLEDGE_BASE, kb_name, doc.id)
        return stored or rebuilt
