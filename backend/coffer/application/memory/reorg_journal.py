"""Journal-side helpers for the reorg pass's 固化 (consolidation) step (007).

Holds the agent system prompt and the read-only journal-lane accessors the
``ReorgService`` loop uses to decide what recurring patterns to promote into the
semantic lane. Kept in a sibling module so ``reorg.py`` stays within the backend
file-size budget. Pure read I/O over ``journal/<period>.md`` files — no LLM, no
mutation (固化 copies; the journal is append-only).
"""

from __future__ import annotations

from pathlib import Path

from coffer.domain.memory.journal import JournalEntry
from coffer.infrastructure.knowledge.paths import journal_dir
from coffer.infrastructure.memory.journal_files import read_entries

#: Cap on the journal entries surfaced to the loop (newest-first).
REORG_JOURNAL_LIMIT = 200

REORG_SYSTEM = (
    "You maintain a small set of coherent topic documents. FIRST call "
    "list_topics to see what exists, then read_topic for any documents you may "
    "change. Consolidate duplicates: write the merged content (preserving ALL "
    "existing info + human edits — never drop content) into ONE topic, then "
    "supersede the now-redundant duplicate. Split an over-long topic into "
    "focused topics. NEVER regenerate from scratch; integrate. "
    "The system archives every prior version automatically, but still prefer "
    "minimal, careful edits. "
    "You also CONSOLIDATE (固化) the episodic journal into durable memory. Call "
    "read_journal to see recent journal entries (each with its date). When a "
    "durable insight RECURS — roughly 3 or more similar entries across at least "
    "2 distinct days — promote it: if it is factual/semantic, write_topic a "
    "concise knowledge topic capturing it; if it is clearly imperative/"
    "behavioural ('always do X', 'never Y'), append_rule instead. Leave one-off "
    "or rarely-seen events in the journal — do NOT promote noise. Promotion "
    "COPIES into knowledge/rules; it does not remove journal entries. Be "
    "conservative: when in doubt, leave it in the journal. When done, stop."
)


def recent_journal_entries(store_dir: Path) -> list[JournalEntry]:
    """Recent journal entries newest-first, capped at ``REORG_JOURNAL_LIMIT``.

    Reads every ``journal/<period>.md`` file in chronological order, concatenates
    the entries (each file is oldest→newest), reverses to newest-first, and caps
    the slice so a huge journal never floods the loop's context."""
    d = journal_dir(store_dir)
    if not d.exists():
        return []
    entries: list[JournalEntry] = []
    for path in sorted(d.glob("*.md")):
        entries.extend(read_entries(path))
    entries.reverse()
    return entries[:REORG_JOURNAL_LIMIT]


def journal_has_entries(store_dir: Path) -> bool:
    """Whether the store's journal lane holds at least one entry (the 固化
    signal that the loop should run even with no topic docs)."""
    d = journal_dir(store_dir)
    if not d.exists():
        return False
    return any(read_entries(path) for path in sorted(d.glob("*.md")))


__all__ = [
    "REORG_JOURNAL_LIMIT",
    "REORG_SYSTEM",
    "journal_has_entries",
    "recent_journal_entries",
]
