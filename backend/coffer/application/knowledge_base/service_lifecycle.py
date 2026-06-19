"""Document lifecycle orchestration for ``KnowledgeBaseService``.

Split out of ``service.py`` to keep it under the file-size ceiling: the
per-document lock (ADR-028) and the recoverable soft-delete / restore / purge
(ADR-030). Mixed into ``KnowledgeBaseService``, which wires the collaborators
declared below. (Keyword/vector search scope-isolation is done at the SQL layer
by the retrieval facade + index, not here.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import DocumentNotFound, IngestRejected
from coffer.domain.knowledge.document import KIND_KNOWLEDGE_BASE, Document
from coffer.domain.resource import ResourceRef

if TYPE_CHECKING:
    from coffer.application.audit_service import AuditService
    from coffer.application.knowledge_base.pipeline import KBPipeline
    from coffer.application.knowledge_base.pipeline_helpers import DocumentRepoPort
    from coffer.domain.knowledge_base.config import KnowledgeBaseConfig


class KBDocumentLifecycleMixin:
    """Lock / soft-delete / restore / purge + search scope-isolation.

    A behavior mixin for ``KnowledgeBaseService`` (which owns the collaborators
    declared below); split here only for the file-size ceiling."""

    if TYPE_CHECKING:  # collaborators provided by KnowledgeBaseService.__init__
        _pipeline: KBPipeline
        _audit: AuditService
        _documents: DocumentRepoPort

        async def get_kb_config(self, kb_name: str) -> KnowledgeBaseConfig: ...
        async def _require_document(
            self, kb_name: str, document_id: str, *, include_deleted: bool = False
        ) -> Document: ...
        def _ensure_unlocked(self, kb_name: str, doc: Document) -> None: ...

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

    async def delete_document(self, *, kb_name: str, document_id: str, actor: str) -> None:
        """Delete a document (ADR-030). A LIVE document is soft-deleted (moved to
        the recoverable trash); an ALREADY-TRASHED document is purged for good."""
        await self.get_kb_config(kb_name)
        doc = await self._require_document(kb_name, document_id, include_deleted=True)
        self._ensure_unlocked(kb_name, doc)
        if doc.deleted_at is not None:
            await self._pipeline.purge(kb_name=kb_name, doc=doc)
            event = AuditEventType.KB_DOCUMENT_PURGED
        else:
            await self._pipeline.soft_delete(kb_name=kb_name, doc=doc)
            event = AuditEventType.KB_DOCUMENT_DELETED
        await self._audit.record(
            event.value,
            ref=ResourceRef(KIND_KNOWLEDGE_BASE, kb_name),
            actor=actor,
            details={"document_id": document_id, "title": doc.title},
        )

    async def restore_document(self, *, kb_name: str, document_id: str, actor: str) -> Document:
        """Restore a trashed document (ADR-030): re-convert from its kept ``raw/``
        original and clear the tombstone. 404 if it is not in the trash."""
        config = await self.get_kb_config(kb_name)
        doc = await self._require_document(kb_name, document_id, include_deleted=True)
        if doc.deleted_at is None:
            raise DocumentNotFound(kb_name, document_id)
        self._ensure_unlocked(kb_name, doc)
        # If a live document now occupies this filename in the same scope (e.g. a
        # re-upload after the delete), restoring would create two live docs with
        # the same original_filename — violating the (kb, project) uniqueness the
        # re-upload match relies on. Refuse rather than silently duplicate.
        filename = str(doc.metadata.get("original_filename", ""))
        if filename:
            clash = await self._documents.find_by_filename(
                KIND_KNOWLEDGE_BASE, kb_name, doc.project_id, filename
            )
            if clash is not None and clash.id != doc.id:
                raise IngestRejected(
                    "duplicate",
                    f"a live document named {filename!r} already exists in this "
                    "scope; delete or rename it before restoring this one",
                )
        restored = await self._pipeline.restore(kb_name=kb_name, doc=doc, config=config)
        await self._audit.record(
            AuditEventType.KB_DOCUMENT_RESTORED.value,
            ref=ResourceRef(KIND_KNOWLEDGE_BASE, kb_name),
            actor=actor,
            details={"document_id": document_id, "title": restored.title},
        )
        return restored
