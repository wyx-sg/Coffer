"""What has been sorted out of the memory hub: ``vault/memory/sorted/<id>.md``
(spec memory "Sort task material into knowledge on request").

One file per hub entry, written when the person's agent sorts the entry
during **Sort into knowledge**: where it went (``knowledge``, ``skill``,
``memory`` or ``drop``), a free-text pointer to the place, and when. The files
are vault content, so vault sync carries them and no other machine asks again.
A record stays when its memory is reworded (Codex rewrites its task groups
often); one whose memory left the hub is pruned by the next sync.

The hub reader walks only ``global/`` and ``projects/``, so these files are
never read as memories.
"""

from __future__ import annotations

import logging
import os
import pathlib
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass

from coffer.domain.memory.errors import UnsafeMemoryPath
from coffer.domain.memory.hub import check_id
from coffer.domain.vault.content_ids import fingerprint
from coffer.domain.vault.layout import MEMORY
from coffer.domain.vault.writers import WRITER_MEMORY_SYNC, CommitMeta
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.memory.frontmatter import render_frontmatter, split_frontmatter
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.writer import VaultWriter

logger = logging.getLogger(__name__)

#: The hub-relative folder the records live in.
SORTED = "sorted"
#: The operation a sorting commit names; its writer is ``memory-sync``.
OP_MEMORY_SORT = "memory-sort"

OUTCOME_KNOWLEDGE = "knowledge"
OUTCOME_SKILL = "skill"
OUTCOME_MEMORY = "memory"
OUTCOME_DROP = "drop"
OUTCOMES = (OUTCOME_KNOWLEDGE, OUTCOME_SKILL, OUTCOME_MEMORY, OUTCOME_DROP)


@dataclass(frozen=True)
class SortedRecord:
    id: str
    outcome: str
    #: Where it went, as the agent named it (a collection and page, a skill).
    where: str
    sorted_at: str
    actor: str = ""


def render_record(record: SortedRecord) -> str:
    fm = {
        "id": record.id,
        "outcome": record.outcome,
        "where": record.where,
        "sorted_at": record.sorted_at,
        "actor": record.actor,
    }
    return render_frontmatter(fm, "")


def parse_record(text: str) -> SortedRecord | None:
    fm, _ = split_frontmatter(text)
    try:
        record_id = check_id(str(fm.get("id", "")))
    except UnsafeMemoryPath:
        return None
    outcome = str(fm.get("outcome", "") or "")
    if outcome not in OUTCOMES:
        return None
    return SortedRecord(
        id=record_id,
        outcome=outcome,
        where=str(fm.get("where", "") or ""),
        sorted_at=str(fm.get("sorted_at", "") or ""),
        actor=str(fm.get("actor", "") or ""),
    )


class SortedStore:
    """``vault/memory/sorted/``, read from disk and written through the vault."""

    def __init__(self, writer: Callable[[], VaultWriter] = vault_writer) -> None:
        self._writer = writer

    def root(self) -> pathlib.Path:
        return self._writer().repo.root / MEMORY / SORTED

    def records(self) -> dict[str, SortedRecord]:
        """Every sorting, by hub entry id. A file that does not parse is skipped."""
        found: dict[str, SortedRecord] = {}
        for path in _md_files(self.root()):
            try:
                record = parse_record(path.read_bytes().decode("utf-8"))
            except (OSError, UnicodeDecodeError):
                logger.warning("memory.sorted.unreadable path=%s", path)
                continue
            if record is not None and record.id == path.stem:
                found[record.id] = record
        return found

    def record(self, records: Iterable[SortedRecord], actor: str | None) -> str | None:
        """Write ``records`` as one vault commit; answer the commit or ``None``."""
        records = list(records)
        if not records:
            return None
        writer = self._writer()
        meta = CommitMeta(
            writer=WRITER_MEMORY_SYNC,
            operation=OP_MEMORY_SORT,
            summary=f"Sorted {len(records)} memor{'y' if len(records) == 1 else 'ies'}",
            actor=actor,
        )
        with writer.begin(meta) as txn:
            for rec in records:
                path = _path(rec.id)
                data = render_record(rec).encode("utf-8")
                current = writer.read_disk(path)
                if current == data:
                    continue
                txn.write(
                    path, data, fingerprint(current) if current is not None else Expect.ABSENT
                )
        return txn.version

    def prune(self, keep: Collection[str], actor: str | None) -> int:
        """Delete the records whose memory left the hub; answer how many."""
        writer = self._writer()
        stale = [i for i in self.records() if i not in keep]
        if not stale:
            return 0
        meta = CommitMeta(
            writer=WRITER_MEMORY_SYNC,
            operation=OP_MEMORY_SORT,
            summary=f"Forgot {len(stale)} sorting record(s) of memories that are gone",
            actor=actor,
        )
        with writer.begin(meta) as txn:
            for record_id in stale:
                path = _path(record_id)
                current = writer.read_disk(path)
                if current is not None:
                    txn.delete(path, fingerprint(current))
        return len(stale)


def _path(record_id: str) -> str:
    return f"{MEMORY}/{SORTED}/{check_id(record_id)}.md"


def _md_files(root: pathlib.Path) -> Iterable[pathlib.Path]:
    try:
        names = os.listdir(root)
    except OSError:
        return []
    return [root / n for n in sorted(names) if n.endswith(".md") and not n.startswith(".")]


__all__ = [
    "OUTCOMES",
    "OUTCOME_DROP",
    "OUTCOME_KNOWLEDGE",
    "OUTCOME_MEMORY",
    "OUTCOME_SKILL",
    "SORTED",
    "SortedRecord",
    "SortedStore",
]
