"""Converting one upload and writing its two files.

The first and last steps of an ingest, kept out of ``pipeline.py`` so that
module stays under the project's file-size ceiling: convert the bytes to
Markdown, then write the normalized ``inbox/<doc-id>.md`` alongside the
untouched original in ``.raw/`` (which is what makes a later re-conversion
possible).
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime

from coffer.application.knowledge.pipeline_helpers import (
    KnowledgePaths,
    Prepared,
    extension_of,
    mkparent_write,
    render_ingest_markdown,
    title_of,
)
from coffer.domain.knowledge.converter import MarkdownConverter
from coffer.infrastructure.knowledge.fs import atomic_write_bytes
from coffer.infrastructure.knowledge.ids import new_ulid


async def prepare_upload(
    converters: MarkdownConverter, filename: str, raw_bytes: bytes
) -> Prepared:
    """Hash, convert, and title one upload before anything is persisted."""
    source_sha = hashlib.sha256(raw_bytes).hexdigest()
    ext = extension_of(filename)
    fmt = ext.lstrip(".") or filename.rsplit(".", 1)[-1].lower()
    markdown, meta = await converters.convert(raw_bytes, fmt)
    body = markdown.strip()
    return Prepared(
        # Stable ULID, decoupled from content (spec knowledge FR-062); a re-upload reuses the
        # matched document's existing id.
        doc_id=new_ulid(),
        source_sha256=source_sha,
        extension=ext,
        markdown=body,
        title=title_of(body, filename),
        conversion_engine=str(meta.get("conversion_engine", "unknown")),
    )


async def write_ingested_files(
    paths: KnowledgePaths,
    scope_name: str,
    doc_id: str,
    prepared: Prepared,
    raw_bytes: bytes,
    filename: str,
    *,
    created_at: datetime,
    updated_at: datetime,
    source_path: str | None = None,
) -> None:
    """Write ``.raw/<doc-id>.<ext>`` and the normalized ``inbox/<doc-id>.md``."""
    await asyncio.to_thread(
        atomic_write_bytes, paths.raw_path(scope_name, doc_id, prepared.extension), raw_bytes
    )
    full = render_ingest_markdown(
        prepared,
        filename,
        created_at=created_at,
        updated_at=updated_at,
        source_path=source_path,
    )
    await asyncio.to_thread(mkparent_write, paths.doc_path(scope_name, doc_id), full)
