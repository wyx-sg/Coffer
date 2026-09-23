"""The verbatim half of a partition: ``.raw/``, written by aggregation alone.

Kept apart from :mod:`coffer.infrastructure.memory.store` for the reason the two
halves exist at all. A partition's four files have **one writer each** (see
"Keep distil out of the raw directory"), and the sharpest way to keep that
checkable is for the one directory only aggregation may touch to be the one
module only aggregation imports: "does the distil pass write ``.raw/``?" is then
answered by reading its import list, not by trusting a comment.

What lands here is an agent's own words, byte for byte (see "Keep raw entries
verbatim and hidden"). That is what lets a bad distillation be re-run without
going back to the agents — and it is why
:mod:`coffer.infrastructure.memory.frontmatter` reflows nothing, unlike
knowledge's own copy of the same idea.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from coffer.domain.error_base import CofferError
from coffer.domain.memory.note import Origin, origin_key
from coffer.domain.memory.reader import RawEntry
from coffer.infrastructure.memory import paths
from coffer.infrastructure.memory.frontmatter import (
    atomic_write,
    read_text,
    render_frontmatter,
    split_frontmatter,
    text_list,
)


class RawEntryNotFound(CofferError):  # noqa: N818
    code = "MEMORY_RAW_ENTRY_NOT_FOUND"

    def __init__(self, partition: str, entry_id: str) -> None:
        super().__init__(f"no raw entry {entry_id!r} in partition {partition!r}")
        self.partition = partition
        self.entry_id = entry_id


@dataclass(frozen=True)
class StoredRawEntry:
    """One raw entry as it sits under ``.raw/``: what a reader said, plus where.

    A :class:`~coffer.domain.memory.reader.RawEntry` carries no provenance,
    because a reader does not know which agent it is being run for; the file on
    disk must carry it anyway, since a note's provenance points here to answer
    *which of my agents already knows this*. :attr:`entry_id` is derived rather
    than passed in, so a note's origin and the raw file it names cannot drift
    apart, and a second pass over an unchanged source overwrites one file rather
    than accumulating a near-duplicate (see "Let only aggregation write raw
    entries").
    """

    partition: str
    agent: str
    native_path: str
    captured_at: str
    entry: RawEntry

    @property
    def entry_id(self) -> str:
        return origin_key(self.agent, self.native_path, self.entry.anchor)

    @property
    def origin(self) -> Origin:
        """This entry as a note's provenance would name it."""
        return Origin(
            agent=self.agent,
            native_path=self.native_path,
            anchor=self.entry.anchor,
            captured_at=self.captured_at,
            source_written_at=self.entry.source_written_at,
        )


def write_raw_entry(stored: StoredRawEntry) -> str:
    """Write one verbatim entry under ``.raw/``. Returns the relative path.

    Only aggregation may call this (see "Let only aggregation write raw
    entries"), and the body goes down exactly as the reader handed it over —
    which is what lets a bad distillation be re-run without going back to the
    agents.
    """
    entry = stored.entry
    frontmatter: dict[str, Any] = {
        "title": entry.title,
        "description": entry.description,
        "type": entry.type,
        "agent": stored.agent,
        "native_path": stored.native_path,
        "anchor": entry.anchor,
        "captured_at": stored.captured_at,
        "source_written_at": entry.source_written_at,
        "project_root": entry.project_root,
        "search_terms": list(entry.search_terms),
    }
    path = paths.raw_path(stored.partition, stored.entry_id)
    atomic_write(path, render_frontmatter(frontmatter, entry.body))
    return paths.relative_of(path)


def read_raw_entry(partition: str, entry_id: str) -> StoredRawEntry:
    """Read one raw entry back. Raises :class:`RawEntryNotFound` when absent."""
    path = paths.raw_path(partition, entry_id)
    if not path.is_file():
        raise RawEntryNotFound(partition, entry_id)
    fm, body = split_frontmatter(read_text(path))
    return StoredRawEntry(
        partition=partition,
        agent=str(fm.get("agent", "")),
        native_path=str(fm.get("native_path", "")),
        captured_at=str(fm.get("captured_at", "")),
        entry=RawEntry(
            title=str(fm.get("title", "")),
            description=str(fm.get("description", "")),
            type=str(fm.get("type", "")),
            body=body,
            anchor=str(fm.get("anchor", "")),
            project_root=str(fm.get("project_root", "")),
            source_written_at=str(fm.get("source_written_at", "")),
            search_terms=text_list(fm.get("search_terms")),
        ),
    )


def list_raw_entries(partition: str) -> tuple[StoredRawEntry, ...]:
    """Every raw entry in ``partition``, ordered by id for a stable listing."""
    directory = paths.raw_dir(partition)
    if not directory.is_dir():
        return ()
    ids = sorted(p.stem for p in directory.glob("*.md"))
    return tuple(read_raw_entry(partition, entry_id) for entry_id in ids)


def delete_raw_entry(partition: str, entry_id: str) -> bool:
    """Remove one raw entry's file; ``True`` when there was one to remove.

    Per entry, with no partition-wide counterpart: a pass never re-reads a
    source whose digest is unchanged (see "Skip unchanged sources"), so a "clear
    the partition and write this pass's entries" helper would delete what the
    skip had just decided was still good.
    """
    path = paths.raw_path(partition, entry_id)
    if not path.is_file():
        return False
    path.unlink()
    return True
