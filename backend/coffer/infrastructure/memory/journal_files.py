# backend/coffer/infrastructure/memory/journal_files.py
"""On-disk journal lane: append-only, time-partitioned ``journal/<YYYY-MM>.md``.

Files-as-truth. Each entry is delimited by an HTML-comment marker line
``<!-- coffer:journal <iso> -->`` (invisible in rendered markdown, and immune to
``##``/list collisions in bodies), followed by the entry body. Append rewrites
the whole file atomically via ``infrastructure.knowledge.fs.atomic_write_text``
so a crash never leaves a partial file. No LLM, no frontmatter — pure I/O.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from coffer.domain.memory.journal import JournalEntry
from coffer.infrastructure.knowledge.fs import atomic_write_text

_MARK = "<!-- coffer:journal "
_ENTRY_RE = re.compile(r"^<!-- coffer:journal (.+?) -->$", re.MULTILINE)


def journal_period(when: datetime) -> str:
    """The time-partition key for ``when`` — ``YYYY-MM`` (one file per month)."""
    return when.strftime("%Y-%m")


def append_entry(path: Path, *, timestamp: datetime, body: str) -> None:
    """Append one timestamped entry to ``path`` atomically (creates parents)."""
    block = f"{_MARK}{timestamp.isoformat()} -->\n{body.strip()}\n"
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


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
