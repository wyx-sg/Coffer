"""External-source tracking for the KB face (FR-021..024).

Extracted from ``service.py`` so the orchestration service stays under the
file-size ceiling. These are the bodies of ``KnowledgeBaseService.check_sources``
/ ``update_from_source``; the service keeps thin delegating wrappers. The host
service is passed in so re-ingest funnels through the existing ``ingest_bytes``
re-upload path (preserving the ULID id + the ``KB_DOCUMENT_UPDATED`` audit).
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from coffer.application.knowledge_base.pipeline_helpers import SourceStatus
from coffer.domain.errors import IngestRejected, ReconversionBlocked
from coffer.domain.knowledge.document import KIND_KNOWLEDGE_BASE, Document

if TYPE_CHECKING:
    from coffer.application.knowledge_base.service import KnowledgeBaseService

_HASH_CHUNK_BYTES = 64 * 1024


def hash_file(source_path: str) -> str | None:
    """sha256 of an external file, streamed in 64 KB chunks so a multi-GB
    original is never read fully into memory. Returns ``None`` when the file
    cannot be read — gone, a directory, permission-denied, or a broken symlink —
    so one pathological source is reported ``"missing"`` and never crashes the
    scan (opening directly also avoids a ``Path.exists`` TOCTOU). The streamed
    digest equals the digest of the full bytes, so it matches the stored
    ``source_sha256``."""
    digest = hashlib.sha256()
    try:
        with Path(source_path).open("rb") as fp:
            while True:
                chunk = fp.read(_HASH_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


async def check_sources(
    service: KnowledgeBaseService, *, kb_name: str, actor: str
) -> list[SourceStatus]:
    """Detect whether each path-tracked document's external original has changed
    on disk, by re-hashing the file and comparing to the stored ``source_sha256``
    provenance.

    Only documents whose ``metadata.source_path`` is set (a path-based ingest
    recorded one) are checked. Detection alone changes nothing and audits
    nothing. When the KB's ``auto_update_sources`` is true, a changed document
    whose ``source_mode != "edited"`` is refreshed in place via
    ``update_from_source`` (which audits the existing ``KB_DOCUMENT_UPDATED``); a
    changed hand-edited document is left alone and reported as ``"edited"``.
    On-demand only — there is no watcher."""
    config = await service.get_kb_config(kb_name)
    docs = await service._documents.list_documents(
        KIND_KNOWLEDGE_BASE, kb_name, limit=100_000, offset=0
    )
    results: list[SourceStatus] = []
    for doc in docs:
        # `or ""` (not a default arg) so a present-but-None value — which a
        # reindex-from-frontmatter rebuild could leave on a byte-upload doc —
        # is skipped rather than stringified to a phantom "None" path.
        source_path = str(doc.metadata.get("source_path") or "")
        if not source_path:
            continue
        stored_sha = str(doc.metadata.get("source_sha256", ""))
        digest = await asyncio.to_thread(hash_file, source_path)
        if digest is None:
            status = "missing"
        elif digest == stored_sha:
            status = "unchanged"
        else:
            status = "changed"
        if status == "changed" and config.auto_update_sources:
            if doc.source_mode == "edited":
                # A hand-edited document is never clobbered by auto-update.
                status = "edited"
            else:
                try:
                    await update_from_source(
                        service, kb_name=kb_name, document_id=doc.id, actor=actor
                    )
                    status = "updated"
                except (IngestRejected, OSError):
                    # A changed source that can't be re-ingested now (became
                    # empty / oversize / unsupported / unreadable) is left as
                    # "changed" for the user to resolve — one bad source must
                    # not abort the rest of the scan.
                    status = "changed"
        results.append(
            SourceStatus(
                doc_id=doc.id,
                title=doc.title,
                source_path=source_path,
                status=status,
            )
        )
    return results


async def update_from_source(
    service: KnowledgeBaseService, *, kb_name: str, document_id: str, actor: str
) -> Document:
    """Re-ingest a document from its tracked external original in place.

    Reads the tracked file's bytes off-thread and replays the existing
    ``replace=True`` re-ingest path, so identity (the ULID id) is preserved and
    the document is re-chunked/re-indexed from the fresh source. Refused for a
    hand-edited document via ``ReconversionBlocked`` so edits are never clobbered.
    Reuses ``IngestRejected`` for the no-source (``no_source``) and vanished-file
    (``source_missing``) cases."""
    await service.get_kb_config(kb_name)
    doc = await service._require_document(kb_name, document_id)
    if doc.source_mode == "edited":
        raise ReconversionBlocked(kb_name, document_id)
    source_path = str(doc.metadata.get("source_path", ""))
    if not source_path:
        raise IngestRejected("no_source", "document has no tracked source_path")
    path = Path(source_path)
    if not await asyncio.to_thread(path.exists):
        raise IngestRejected("source_missing", f"tracked source file is missing: {source_path}")
    raw = await asyncio.to_thread(path.read_bytes)
    return await service.ingest_bytes(
        kb_name=kb_name,
        filename=str(doc.metadata["original_filename"]),
        raw_bytes=raw,
        actor=actor,
        replace=True,
        source_path=source_path,
    )
