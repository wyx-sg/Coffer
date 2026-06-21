# backend/coffer/infrastructure/memory/journal_files.py
"""On-disk journal lane: append-only, time-partitioned ``journal/<YYYY-MM>.md``.

Files-as-truth. Each entry is delimited by an HTML-comment marker line
``<!-- coffer:journal <iso> -->`` (invisible in rendered markdown, and immune to
``##``/list collisions in bodies), followed by the entry body. Append rewrites
the whole file atomically via ``infrastructure.knowledge.fs.atomic_write_text``
so a crash never leaves a partial file. No LLM, no frontmatter — pure I/O.

``scan_journal_dir`` additionally projects each period file into one indexable
``JournalFileScan`` so the memory reconciler can index the journal lane for
``recall`` (FR-043), chunked like a topic doc.

**Known limitation — reserved delimiter in body text.**
The marker line ``<!-- coffer:journal <iso> -->`` is reserved as an entry
delimiter. A body whose own text contains that exact pattern on a line by itself
will be mis-parsed by ``read_entries`` as the start of a new entry. This is an
accepted limitation for the lane's scope: bodies are Coffer-internal episodic
text produced by the application, not arbitrary user markdown, so the pattern
will not appear naturally. No escaping or validation is applied; callers must
not embed the marker pattern in body text.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from coffer.domain.memory.journal import JournalEntry
from coffer.infrastructure.knowledge.fs import atomic_write_text
from coffer.infrastructure.knowledge.paths import journal_dir

_MARK = "<!-- coffer:journal "
_ENTRY_RE = re.compile(r"^<!-- coffer:journal (.+?) -->$", re.MULTILINE)


def journal_period(when: datetime) -> str:
    """The time-partition key for ``when`` — ``YYYY-MM`` (one file per month)."""
    return when.strftime("%Y-%m")


def journal_doc_id(period: str) -> str:
    """Stable ``documents``-row id for a period file (e.g. ``journal-2026-06``).

    Shared by the reconciler (keyword/vector index) and the grep guard so a
    keyword and a grep hit on the same month dedupe to one recall result. The
    ``journal-`` prefix never collides with a fact's ULID id."""
    return f"journal-{period}"


def append_entry(path: Path, *, timestamp: datetime, body: str) -> None:
    """Append one timestamped entry to ``path`` atomically (creates parents)."""
    block = f"{_MARK}{timestamp.isoformat()} -->\n{body.strip('\n')}\n"
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError:
        existing = ""
    path.parent.mkdir(parents=True, exist_ok=True)
    sep = "" if not existing or existing.endswith("\n") else "\n"
    atomic_write_text(path, existing + sep + block)


def read_entries(path: Path) -> list[JournalEntry]:
    """Parse all entries from ``path`` in file order (oldest→newest); ``[]`` if
    the file does not exist."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    matches = list(_ENTRY_RE.finditer(text))
    entries: list[JournalEntry] = []
    for i, m in enumerate(matches):
        ts = _parse_ts(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        entries.append(JournalEntry(timestamp=ts, body=text[start:end].strip("\n")))
    return entries


@dataclass(frozen=True)
class JournalFileScan:
    """One period file projected into an indexable memory document (FR-043).

    The reconciler indexes ``body`` (chunked like a topic doc) under ``doc_id``
    and stores ``path`` as the document's ``source`` so a recall hit points back
    at the canonical ``journal/<period>.md`` file."""

    doc_id: str
    period: str
    path: Path
    title: str
    body: str
    content_sha256: str
    created_at: datetime
    updated_at: datetime


def scan_journal_dir(store_dir: Path) -> dict[str, JournalFileScan]:
    """Project every ``journal/<period>.md`` file into a ``JournalFileScan``,
    keyed by ``journal_doc_id``. The lane may not exist yet (no episodic events)
    → an empty dict, never an error. Empty/entry-less files are skipped."""
    out: dict[str, JournalFileScan] = {}
    d = journal_dir(store_dir)
    if not d.exists():
        return out
    for path in sorted(d.glob("*.md")):
        entries = read_entries(path)
        if not entries:
            continue
        period = path.stem
        body = _indexable_body(entries)
        out[journal_doc_id(period)] = JournalFileScan(
            doc_id=journal_doc_id(period),
            period=period,
            path=path,
            title=f"Journal {period}",
            body=body,
            content_sha256=_body_sha256(body),
            created_at=entries[0].timestamp,
            updated_at=entries[-1].timestamp,
        )
    return out


def _indexable_body(entries: list[JournalEntry]) -> str:
    """A clean, chunkable body for the index — entry bodies joined with a
    human-readable date prefix (the HTML-comment markers are excluded so they
    never pollute FTS / a recall passage)."""
    return "\n\n".join(f"{e.timestamp.date().isoformat()}: {e.body}" for e in entries)


def _body_sha256(body: str) -> str:
    """Hash of the indexable body — the reindex no-op gate for a journal file.
    Must match ``application.knowledge.reindex.content_sha256`` (same algorithm)
    so the reconciler can compare a fresh scan against the stored row."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
