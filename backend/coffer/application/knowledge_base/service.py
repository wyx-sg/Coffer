"""KnowledgeBaseService — application-level orchestration for KB operations.

Coordinates:
- The kind-agnostic `ResourceService` (KB-as-Resource lifecycle).
- The `KBDocumentRepo` port (kb_documents rows).
- The `KnowledgeBaseStore` port (LlamaIndex-or-fake; see infrastructure/).
- The `AuditService`.
- The `Tracer` (no-op default; LangFuse when configured).
- The file-system layer (only via paths handed in by the composition root).

Knows nothing about LlamaIndex.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.application.observability.tracer import Tracer
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    DocumentNotFound,
    IngestRejected,
    KBNotFound,
)
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.knowledge_base.document import Document
from coffer.domain.knowledge_base.store import KnowledgeBaseStore, Passage
from coffer.domain.resource import ResourceRef


class KBDocumentRepo(Protocol):
    async def create(self, d: Document) -> Document: ...
    async def list_by_kb(self, kb_name: str, *, limit: int, offset: int) -> list[Document]: ...
    async def count_by_kb(self, kb_name: str) -> int: ...
    async def get(self, kb_name: str, document_id: str) -> Document | None: ...
    async def exists_by_hash(self, kb_name: str, sha256: str) -> bool: ...
    async def find_by_hash(self, kb_name: str, sha256: str) -> list[Document]: ...
    async def delete(self, kb_name: str, document_id: str) -> bool: ...
    async def delete_all(self, kb_name: str) -> int: ...


# Text-extractor: file path + extension -> extracted text.
# Provided by infrastructure (`loaders.py`); the service doesn't know which
# extension is mapped to which extractor.
TextExtractor = Callable[[Path, str], Awaitable[str]]

# Filesystem helpers the service delegates to.
KBPathLayout = "coffer.infrastructure.knowledge_base.paths"  # documentation only


@dataclass
class _Paths:
    """Filesystem helpers injected by the composition root."""

    raw_dir: Callable[[str], Path]
    raw_file: Callable[[str, str, str], Path]
    kb_dir: Callable[[str], Path]
    kb_root: Callable[[], Path]


@dataclass
class _IngestPreflight:
    document_id: str
    sha256: str
    size_bytes: int


class KnowledgeBaseService:
    def __init__(
        self,
        *,
        resource_service: ResourceService,
        store: KnowledgeBaseStore,
        documents: KBDocumentRepo,
        audit: AuditService,
        tracer: Tracer,
        paths: _Paths,
        extractor: TextExtractor,
    ) -> None:
        self._resources = resource_service
        self._store = store
        self._documents = documents
        self._audit = audit
        self._tracer = tracer
        self._paths = paths
        self._extract = extractor

    @classmethod
    def build(
        cls,
        *,
        resource_service: ResourceService,
        store: KnowledgeBaseStore,
        documents: KBDocumentRepo,
        audit: AuditService,
        tracer: Tracer,
        raw_dir: Callable[[str], Path],
        raw_file: Callable[[str, str, str], Path],
        kb_dir: Callable[[str], Path],
        kb_root: Callable[[], Path],
        extractor: TextExtractor,
    ) -> KnowledgeBaseService:
        return cls(
            resource_service=resource_service,
            store=store,
            documents=documents,
            audit=audit,
            tracer=tracer,
            paths=_Paths(raw_dir=raw_dir, raw_file=raw_file, kb_dir=kb_dir, kb_root=kb_root),
            extractor=extractor,
        )

    # ----- KB-level operations -----

    async def get_kb_config(self, kb_name: str) -> KnowledgeBaseConfig:
        ref = ResourceRef(kind="knowledge_base", name=kb_name)
        try:
            resource = await self._resources.get(ref)
        except Exception as exc:  # ResourceNotFound bubbles as KBNotFound
            raise KBNotFound(kb_name) from exc
        return KnowledgeBaseConfig.model_validate(resource.config)

    # ----- Document-level operations -----

    async def ingest_bytes(
        self,
        *,
        kb_name: str,
        filename: str,
        raw_bytes: bytes,
        actor: str,
        replace: bool = False,
    ) -> Document:
        config = await self.get_kb_config(kb_name)

        if not raw_bytes:
            raise IngestRejected("empty_text", "uploaded file is empty")
        if len(raw_bytes) > config.max_document_bytes:
            raise IngestRejected(
                "too_large",
                f"file size {len(raw_bytes)} bytes exceeds KB limit {config.max_document_bytes}",
            )

        preflight = _hash_file(raw_bytes)
        extension = _extension(filename)

        # Duplicate check FIRST: opening the engine index is expensive (loads
        # the embedding model). Pay that cost only if we will actually ingest
        # something new (CODE22-012).
        is_duplicate = await self._documents.exists_by_hash(kb_name, preflight.sha256)
        if is_duplicate and not replace:
            raise IngestRejected(
                "duplicate",
                "a document with the same content hash already exists; "
                "pass replace=true to overwrite",
            )

        # Open engine. The replace path below needs the index loaded to
        # delete stale entries; otherwise the first post-restart ingest hits
        # the store with no cached config.
        await self._store.open(kb_name, config)
        if is_duplicate:
            await self._delete_by_hash(kb_name, preflight.sha256, actor)

        # Persist raw file.
        raw_path = self._paths.raw_file(kb_name, preflight.document_id, extension)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw_bytes)

        # Extract text. If extraction fails, clean up the raw file.
        try:
            text = await self._extract(raw_path, extension)
        except Exception:
            raw_path.unlink(missing_ok=True)
            raise

        if not text.strip():
            raw_path.unlink(missing_ok=True)
            raise IngestRejected(
                "empty_text",
                "no extractable text from file (unsupported format or empty content)",
            )

        # Index it.
        ingested_at = datetime.now(tz=UTC)
        with self._tracer.span(
            "kb.ingest_document",
            attributes={
                "kb_name": kb_name,
                "size_bytes": len(raw_bytes),
                "char_size": len(text),
            },
        ) as span:
            try:
                temp_doc = Document(
                    id=preflight.document_id,
                    kb_name=kb_name,
                    filename=filename,
                    extension=extension,
                    size_bytes=preflight.size_bytes,
                    sha256=preflight.sha256,
                    chunk_count=0,
                    ingested_at=ingested_at,
                )
                chunk_count = await self._store.ingest(kb_name, temp_doc, text)
            except Exception as exc:
                # Roll back raw file.
                raw_path.unlink(missing_ok=True)
                span.record_error(exc)
                raise
            span.set_attribute("chunk_count", chunk_count)

        # Persist row. Two concurrent ingests can race the UniqueConstraint
        # on ``(kb_name, sha256)``; translate IntegrityError to
        # IngestRejected("duplicate") and clean up the losing side (CODE22-008).
        import sqlalchemy.exc as _sa_exc

        final_doc = Document(
            id=preflight.document_id,
            kb_name=kb_name,
            filename=filename,
            extension=extension,
            size_bytes=preflight.size_bytes,
            sha256=preflight.sha256,
            chunk_count=chunk_count,
            ingested_at=ingested_at,
        )
        try:
            created = await self._documents.create(final_doc)
        except _sa_exc.IntegrityError as exc:
            raw_path.unlink(missing_ok=True)
            # Cleanup is best-effort: the row write lost a race so the index
            # entries written by this losing ingest are now orphaned.
            import contextlib as _contextlib

            with _contextlib.suppress(Exception):
                await self._store.delete_document(kb_name, preflight.document_id)
            raise IngestRejected(
                "duplicate",
                "a document with the same content hash already exists "
                "(concurrent ingest race); pass replace=true to overwrite",
            ) from exc

        await self._audit.record(
            AuditEventType.KB_DOCUMENT_INGESTED.value,
            ref=ResourceRef("knowledge_base", kb_name),
            actor=actor,
            details={
                "document_id": created.id,
                "filename": filename,
                "size_bytes": created.size_bytes,
                "chunk_count": created.chunk_count,
            },
        )
        return created

    async def list_documents(
        self, *, kb_name: str, limit: int, offset: int
    ) -> tuple[list[Document], int]:
        await self.get_kb_config(kb_name)  # raises KBNotFound
        docs = await self._documents.list_by_kb(kb_name, limit=limit, offset=offset)
        total = await self._documents.count_by_kb(kb_name)
        return docs, total

    async def get_document_text(self, *, kb_name: str, document_id: str) -> tuple[Document, str]:
        doc = await self._documents.get(kb_name, document_id)
        if doc is None:
            raise DocumentNotFound(kb_name, document_id)
        raw_path = self._paths.raw_file(kb_name, doc.id, doc.extension)
        if not raw_path.exists():
            raise DocumentNotFound(kb_name, document_id)
        text = await self._extract(raw_path, doc.extension)
        return doc, text

    async def delete_document(self, *, kb_name: str, document_id: str, actor: str) -> None:
        doc = await self._documents.get(kb_name, document_id)
        if doc is None:
            raise DocumentNotFound(kb_name, document_id)
        # Remove from index first.
        await self._store.delete_document(kb_name, document_id)
        # Remove raw file.
        raw_path = self._paths.raw_file(kb_name, doc.id, doc.extension)
        raw_path.unlink(missing_ok=True)
        # Remove DB row.
        await self._documents.delete(kb_name, document_id)
        # Audit.
        await self._audit.record(
            AuditEventType.KB_DOCUMENT_DELETED.value,
            ref=ResourceRef("knowledge_base", kb_name),
            actor=actor,
            details={"document_id": document_id, "filename": doc.filename},
        )

    async def search(self, *, kb_name: str, query: str, top_k: int) -> list[Passage]:
        config = await self.get_kb_config(kb_name)
        await self._store.open(kb_name, config)
        with self._tracer.span(
            "kb.search",
            attributes={
                "kb_name": kb_name,
                "query_len": len(query),
                "top_k": top_k,
            },
        ) as span:
            hits = list(await self._store.search(kb_name, query, top_k))
            span.set_attribute("hit_count", len(hits))
        return hits

    async def metrics(self, *, kb_name: str) -> tuple[int, int]:
        import asyncio

        await self.get_kb_config(kb_name)
        doc_count = await self._documents.count_by_kb(kb_name)
        kb_dir = self._paths.kb_dir(kb_name)
        # ``_du`` walks the KB dir, which is O(N) sync I/O. Offload to a
        # worker thread so the event loop keeps serving other requests while
        # the walk runs (CODE22-014). When the directory does not exist yet
        # (KB just created, no docs), short-circuit to 0 without a thread.
        disk = await asyncio.to_thread(_du, kb_dir) if kb_dir.exists() else 0
        return doc_count, disk

    # ----- Used by the kind on_delete hook -----

    async def cleanup_kb(self, kb_name: str) -> None:
        """Sync deletion path: drop the index, remove rows, rmtree the dir.

        Defense-in-depth: even though Resource name validation rejects path
        separators, the rmtree target is re-checked here against the configured
        kb_root() so a name of ``..`` (or anything else that escapes the root)
        cannot wipe ``~/.coffer/`` if validation is ever relaxed (CODE22-005).
        """
        import shutil

        await self._store.drop(kb_name)
        await self._documents.delete_all(kb_name)
        kb_dir = self._paths.kb_dir(kb_name)
        if not kb_dir.exists():
            return
        # Re-validate that ``kb_dir`` is strictly under ``kb_root`` before
        # rmtree. ``relative_to`` raises ValueError if escape is attempted.
        resolved = kb_dir.resolve()
        root_resolved = self._paths.kb_root().resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            # Refuse to recurse outside the configured KB root.
            return
        if resolved == root_resolved:
            return
        shutil.rmtree(resolved, ignore_errors=True)

    # ----- internals -----

    async def _delete_by_hash(self, kb_name: str, sha256: str, actor: str) -> None:
        # Use the indexed UniqueConstraint on ``(kb_name, sha256)`` directly
        # rather than paginating ``list_by_kb`` (previous implementation only
        # scanned the first 1000 rows — CODE22-010).
        for doc in await self._documents.find_by_hash(kb_name, sha256):
            await self.delete_document(kb_name=kb_name, document_id=doc.id, actor=actor)


def _hash_file(raw: bytes) -> _IngestPreflight:
    h = hashlib.sha256(raw).hexdigest()
    return _IngestPreflight(document_id=h[:16], sha256=h, size_bytes=len(raw))


# Only return extensions matching a strict alnum-after-single-dot shape.
# Anything else (e.g. ``./../../etc/passwd`` from a filename like
# ``foo./../../etc/passwd``) is dropped to empty so ``raw_file_path`` cannot
# be tricked into escaping ``kb_raw_dir`` (CODE22-006).
_SAFE_EXT_PATTERN = re.compile(r"^\.[A-Za-z0-9]{1,16}$")


def _extension(filename: str) -> str:
    idx = filename.rfind(".")
    if idx == -1:
        return ""
    candidate = filename[idx:].lower()
    if not _SAFE_EXT_PATTERN.match(candidate):
        return ""
    return candidate


def _du(path: Path) -> int:
    import contextlib

    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            with contextlib.suppress(OSError):
                total += p.stat().st_size
    return total
