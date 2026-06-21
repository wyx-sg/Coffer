"""Pure helpers + ports for the KB pipeline.

Split out of ``pipeline.py`` to keep that module under the file-size ceiling.
These are dependency-light (frontmatter/chunking/path math) and reused by the
service for reads (``read_markdown_body``, ``du_bytes``, ``chunker_for``).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from coffer.domain.errors import IngestRejected
from coffer.domain.knowledge.document import (
    KIND_KNOWLEDGE_BASE,
    WORKSPACE_GLOBAL_PROJECT_ID,
    Document,
)
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.infrastructure.knowledge.chunking import chunk_markdown
from coffer.infrastructure.knowledge.frontmatter import render_frontmatter, split_frontmatter
from coffer.infrastructure.knowledge.fs import atomic_write_text

# A filename's extension, lower-cased, restricted to a safe shape so it can never
# escape ``raw/`` (e.g. ``foo./../../etc``).
_SAFE_EXT = re.compile(r"^\.[A-Za-z0-9]{1,16}$")


class DocumentRepoPort(Protocol):
    """The document-row repo surface used by the KB face (a subset of the
    infrastructure ``DocumentRepo`` plus ``count_chunks``)."""

    async def upsert_document(self, d: Document) -> Document: ...
    async def get_document(self, kind: str, resource_name: str, doc_id: str) -> Document | None: ...
    async def list_documents(
        self, kind: str, resource_name: str, *, limit: int, offset: int, q: str | None = None
    ) -> list[Document]: ...
    async def count_documents(
        self, kind: str, resource_name: str, *, q: str | None = None
    ) -> int: ...
    async def count_pending_embeds(self, kind: str, resource_name: str) -> int: ...
    async def count_chunks(self, kind: str, resource_name: str) -> int: ...
    async def chunk_counts(self, kind: str, resource_name: str) -> dict[str, int]: ...
    async def find_by_filename(
        self, kind: str, resource_name: str, project_id: str, original_filename: str
    ) -> Document | None: ...
    async def delete_document(self, kind: str, resource_name: str, doc_id: str) -> bool: ...
    async def delete_resource(self, kind: str, resource_name: str) -> int: ...


class KBPaths(Protocol):
    """The on-disk path layout (injected — ``infrastructure.knowledge.paths``)."""

    def kb_dir(self, name: str) -> Path: ...
    def docs_dir(self, name: str) -> Path: ...
    def raw_dir(self, name: str) -> Path: ...
    def doc_path(self, name: str, doc_id: str) -> Path: ...
    def raw_path(self, name: str, doc_id: str, ext: str) -> Path: ...
    def knowledge_root(self) -> Path: ...


@dataclass
class Prepared:
    """The result of converting one uploaded file before it is persisted."""

    doc_id: str
    source_sha256: str
    extension: str
    markdown: str
    title: str
    conversion_engine: str


@dataclass(frozen=True)
class SourceStatus:
    """One document's external-source tracking status (``check_sources`` result).

    ``status`` is one of ``"unchanged"`` (the tracked external file's sha256
    matches the stored ``source_sha256``), ``"changed"`` (it differs),
    ``"missing"`` (the tracked file is gone), ``"edited"`` (changed but skipped
    because the document was hand-edited), or ``"updated"`` (a changed source
    that ``auto_update_sources`` re-ingested in place)."""

    doc_id: str
    title: str
    source_path: str
    status: str


def check_upload_size(raw_bytes: bytes, config: KnowledgeBaseConfig) -> None:
    """Reject an empty or over-limit upload before any conversion work."""
    if not raw_bytes:
        raise IngestRejected("empty", "uploaded file is empty")
    if len(raw_bytes) > config.max_document_bytes:
        raise IngestRejected(
            "too_large",
            f"file size {len(raw_bytes)} exceeds KB limit {config.max_document_bytes}",
        )


def mkparent_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp file + fsync + ``os.replace``),
    creating parent dirs — so a crash never leaves a partial source-of-truth file."""
    atomic_write_text(path, text)


def extension_of(filename: str) -> str:
    """A safe lower-cased ``.ext`` (or empty), guarding against path escape."""
    idx = filename.rfind(".")
    if idx == -1:
        return ""
    candidate = filename[idx:].lower()
    return candidate if _SAFE_EXT.match(candidate) else ""


def title_of(markdown: str, fallback: str) -> str:
    """First heading / first non-blank line / ``fallback``."""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:200] or fallback
        if stripped:
            return stripped[:200]
    return fallback


def chunker_for(config: KnowledgeBaseConfig) -> Callable[[str], list[str]]:
    """A markdown-aware chunker closure bound to the KB's chunk params."""

    def _chunk(markdown: str) -> list[str]:
        return chunk_markdown(
            markdown, chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap
        )

    return _chunk


def read_markdown_body(full: str) -> str:
    """The markdown body of a ``docs/<id>.md`` file (frontmatter stripped)."""
    _, body = split_frontmatter(full)
    return body


def du_bytes(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            with contextlib.suppress(OSError):
                total += p.stat().st_size
    return total


def docs_fingerprint(docs_dir: Path) -> str:
    """A cheap, stat-only fingerprint of a KB's ``docs/`` directory.

    Globs ``docs/*.md`` and hashes the sorted
    ``(name, st_mtime_ns, st_ctime_ns, st_size)`` tuples — NO file reads, NO
    frontmatter parse. The digest changes whenever ANY ``*.md`` file is added,
    removed, renamed, or written to: a normal edit bumps ``st_mtime_ns``, a
    same-length change still moves ``st_size``, and ``st_ctime_ns`` (inode change
    time, which ordinary tooling cannot set) catches an mtime-restoring edit
    (``touch -r`` / ``cp -p`` over a same-size body). The one residual blind spot
    vs. the old read-every-file scan is a same-size content edit that restores
    BOTH mtime and ctime — practically unreachable without clock/root tricks, and
    always caught by an explicit ``coffer kb reindex``. This drops the O(N)
    read+parse cost of a full scan to a stat walk. The empty / missing directory
    has a stable fixed digest.

    Race-safe by construction: a stat walk is idempotent and side-effect-free,
    so two concurrent reads compute the same digest off the same on-disk state.
    """
    h = hashlib.sha256()
    if docs_dir.exists():
        entries: list[tuple[str, int, int, int]] = []
        for p in sorted(docs_dir.glob("*.md")):
            with contextlib.suppress(OSError):
                st = p.stat()
                entries.append((p.name, st.st_mtime_ns, st.st_ctime_ns, st.st_size))
        for name, mtime_ns, ctime_ns, size in entries:
            h.update(f"{name}\0{mtime_ns}\0{ctime_ns}\0{size}\0".encode())
    return h.hexdigest()


async def reconcile_on_read(
    cache: dict[str, str],
    kb_name: str,
    docs_dir: Path,
    scan: Callable[[], Awaitable[dict[str, int]]],
) -> dict[str, int] | None:
    """Lazy reindex-on-read (FR-008a) short-circuit.

    If the cheap stat-only ``docs/`` fingerprint matches ``cache[kb_name]``, the
    corpus is provably unchanged since the last full scan, so the O(N) read+parse
    ``scan`` is skipped and the read is served directly (returns ``None``).
    Otherwise — an out-of-band add/remove/edit bumped it (stat-detected; see
    ``docs_fingerprint``), or it is the first read since daemon start — ``scan`` runs
    (and refreshes the cache itself). The fingerprint only decides WHETHER to
    scan, never WHAT it does.
    """
    current = await asyncio.to_thread(docs_fingerprint, docs_dir)
    if cache.get(kb_name) == current:
        return None
    return await scan()


def _parse_dt(value: object, *, default: datetime) -> datetime:
    """Parse an ISO timestamp string into an aware UTC datetime.

    Missing / blank / unparseable → ``default`` (the file mtime), so a
    pre-existing / hand-written file degrades gracefully. A local copy of the
    memory face's helper (``infrastructure.memory.files._parse_dt``) — the
    import-linter forbids cross-kind imports (memory↔knowledge_base), so each
    kind keeps its own copy (the established pattern)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return default
    return default


def document_from_frontmatter(
    kb_name: str, doc_id: str, frontmatter: dict[str, object], *, mtime: datetime
) -> Document:
    """Rebuild a ``documents`` row from a file's self-describing frontmatter.

    The doc timestamps are read back from the frontmatter (``created_at`` /
    ``updated_at``) so a DB-loss rebuild restores the real ingest/edit time
    instead of resetting to ``now`` — files are the source of truth. A
    pre-existing / hand-written file lacking those keys falls back to the file
    ``mtime`` (not ``now``). ``converted_at`` stays ``now`` — it tracks this
    conversion-engine run, not the document's age."""
    now = datetime.now(tz=UTC)
    created_at = _parse_dt(frontmatter.get("created_at"), default=mtime)
    updated_at = _parse_dt(frontmatter.get("updated_at"), default=mtime)
    source_filename = str(frontmatter.get("source_filename", ""))
    metadata: dict[str, object] = {
        "original_filename": source_filename,
        "original_format": str(frontmatter.get("source_format", "")),
        "source_sha256": str(frontmatter.get("source_sha256", "")),
        "converted_at": now.isoformat(),
        "conversion_engine": str(frontmatter.get("converter", "unknown")),
    }
    # The external original's absolute path, when a path-based ingest recorded
    # one (CLI / desktop picker). Added ONLY when truthy — mirrors
    # build_kb_document so a byte-upload / agent ingest never gains a phantom
    # source_path (a stored None would otherwise surface as a bogus "missing"
    # source on the next check after a reindex-from-frontmatter rebuild).
    source_path = str(frontmatter.get("source_path", ""))
    if source_path:
        metadata["source_path"] = source_path
    return Document(
        id=doc_id,
        kind=KIND_KNOWLEDGE_BASE,
        resource_name=kb_name,
        project_id=WORKSPACE_GLOBAL_PROJECT_ID,
        path=f"docs/{doc_id}.md",
        title=str(frontmatter.get("title", "") or doc_id),
        description=None,
        content_sha256="",  # set by the reindex routine
        source_mode=str(frontmatter.get("source_mode", "converted")),
        created_at=created_at,
        updated_at=updated_at,
        metadata=metadata,
    )


def build_kb_document(
    *,
    kb_name: str,
    doc_id: str,
    prepared: Prepared,
    filename: str,
    source_mode: str,
    created_at: datetime,
    updated_at: datetime,
    source_path: str | None = None,
) -> Document:
    """Build the in-memory ``Document`` for a freshly-converted upload. ``id`` is
    the stable ULID (new for an ingest, reused for an in-place update — ADR-028);
    ``content_sha256`` is set by the reindex routine. ``source_path`` is the
    external original's absolute path, recorded only for path-based ingests."""
    metadata: dict[str, object] = {
        "original_filename": filename,
        "original_format": prepared.extension.lstrip("."),
        "source_sha256": prepared.source_sha256,
        "converted_at": updated_at.isoformat(),
        "conversion_engine": prepared.conversion_engine,
    }
    if source_path:
        metadata["source_path"] = source_path
    return Document(
        id=doc_id,
        kind=KIND_KNOWLEDGE_BASE,
        resource_name=kb_name,
        project_id=WORKSPACE_GLOBAL_PROJECT_ID,
        path=f"docs/{doc_id}.md",
        title=prepared.title,
        description=None,
        content_sha256="",  # set by the reindex routine
        source_mode=source_mode,
        created_at=created_at,
        updated_at=updated_at,
        metadata=metadata,
    )


def render_ingest_markdown(
    prepared: Prepared,
    filename: str,
    *,
    created_at: datetime,
    updated_at: datetime,
    source_path: str | None = None,
) -> str:
    """Render a freshly-converted upload's ``docs/<id>.md`` (frontmatter + body).

    Timestamps live in the file (the source of truth) so a DB-loss rebuild
    restores them; ``source_path`` is recorded only for path-based ingests (a
    byte/agent upload must not gain a server path). Keep this field set
    identical to ``render_doc_markdown`` so an ingest→edit→rebuild round-trip is
    stable."""
    fields: dict[str, object] = {
        "title": prepared.title,
        "source_filename": filename,
        "source_format": prepared.extension.lstrip("."),
        "source_sha256": prepared.source_sha256,
        "converter": prepared.conversion_engine,
        "source_mode": "converted",
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }
    if source_path:
        fields["source_path"] = source_path
    return render_frontmatter(fields, prepared.markdown)


def render_doc_markdown(doc: Document, body: str, *, source_mode: str, updated_at: datetime) -> str:
    """Re-render a document's ``docs/<id>.md`` (frontmatter + body) for an edit
    or reconvert, preserving its provenance metadata. ``created_at`` is carried
    from the document; ``updated_at`` is the new edit/reconvert time. Keep this
    field set identical to ``render_ingest_markdown`` so a round-trip is
    stable."""
    fields: dict[str, object] = {
        "title": title_of(body, doc.title),
        "source_filename": str(doc.metadata.get("original_filename", "")),
        "source_format": str(doc.metadata.get("original_format", "")),
        "source_sha256": str(doc.metadata.get("source_sha256", "")),
        "converter": str(doc.metadata.get("conversion_engine", "")),
        "source_mode": source_mode,
        "created_at": doc.created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }
    # Carry the external-source path through edit/reconvert so source tracking
    # survives those write paths (only present for path-based ingests).
    source_path = doc.metadata.get("source_path")
    if source_path:
        fields["source_path"] = source_path
    return render_frontmatter(fields, body)
