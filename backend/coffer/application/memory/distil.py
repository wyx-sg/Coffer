"""The distil pass: raw entries in, Coffer's own notes out (spec memory "Distil each
raw entry into a note mechanically").

This is the pass the whole layer exists for. Aggregation reads the agents'
native memories and puts what it found under a partition's ``.raw/``,
verbatim; this turns that into ``notes/`` and writes the ``MEMORY.md`` a
session is actually given.

**The pass is mechanical and calls no model.** Each new entry becomes a note of
its own, carrying the source's own title, description, text, type and search
terms, and the index is rendered from the notes' frontmatter. Judgement about
meaning — merging two notes that say one thing, splitting a note that says two,
correcting or retiring one — belongs to the agent the person hands the partition
to (the "Tidying memory" section of the ``coffer-guide`` skill). The pass only
carries out the marks that agent leaves.

**The single most important invariant in this module: a retirement is written
to ``RETIRED.md`` *and* the note file is deleted, and ``RETIRED.md`` is part of
the next pass's input (see "Record retirements so they stick").** Every other rule here
can be got wrong and cost one pass. This one, got wrong, costs every pass forever: the
material a note was built from still lives in the agent's own memory, outside anything
Coffer controls, so the next aggregation reads it again and the next distil pass
re-opens the note this one removed. In a store whose sources live outside it, **an
unrecorded deletion is undone**. ``RETIRED.md`` is not a bin, it is the mechanism.

**A marked note is retired before anything else (see "Retire a note an agent marked
retired").** An agent cannot compute raw entry ids, so it writes ``retired: <reason>``
(and optionally ``replaced_by: <slug>``) into the note's frontmatter. The pass records
the note's origin keys as the retirement's ``entry_ids``, deletes the file, and goes on:
the entries are accounted for, so the next pass does not re-open the subject. A merge
needs no marker: the survivor carries the merged note's origins.

**``.raw/`` is never written here (see "Leave the raw directory to aggregation").** Not
one call: the pass uses ``store.list_raw_entries`` and nothing else from the store's raw
half, which makes the rule checkable by reading the call sites rather than by trusting a
comment. That separation is what lets a bad distillation be re-run without going back to
the agents.

**``MEMORY.md`` is always written.** Even when nothing changed. A pass must never leave
a partition without an index, because the index *is* the delivery (see "Deliver the
index and the notes path at session start") — a partition with notes and no index
delivers nothing.

**Which entries are new.** An entry is undistilled when its ``entry_id``
appears neither in any note's ``origins`` nor in any ``RETIRED.md`` record's
``entry_ids``. Both halves matter. Without the first, every pass re-opens the
whole partition. Without the second, an entry whose note was retired would be
re-offered forever, since a retired entry stays in ``.raw/`` ("Leave the raw directory to
aggregation" forbids deleting it).

**A note whose raw entries are all gone is retired (see "Retire a note whose raw
entries are all gone").** Aggregation deletes a raw entry when its source stops
producing it — the agent deleted the fact, or placement now files it into another
partition — and a note is only derived from what ``.raw/`` holds. So every pass first
retires each note none of whose origins is still in ``.raw/``, and records it in
``RETIRED.md`` with ``sources_gone`` set. That is not an exclusion: the record names no
entry ids, so material that comes back is distilled afresh. A note that still has one
origin standing is left alone.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from coffer.application.memory.distil_sources import (
    SOURCES_GONE_REASON,
    has_distil_work,
    retire_marked,
    retire_sourceless,
    undistilled,
)
from coffer.application.memory.index import render_index
from coffer.application.memory.note_naming import note_type, now, unique_slug
from coffer.domain.memory.note import Note
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory import store
from coffer.infrastructure.memory.raw_store import StoredRawEntry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DistilResult:
    """What one distil pass over one partition did (see "Record what each distil
    pass wrote and retired").

    The counts the audit event and the surfaces carry.
    """

    partition: str
    #: Notes created from raw entries not yet accounted for.
    opened: int
    #: Notes removed from ``notes/`` and recorded in ``RETIRED.md``: those an agent
    #: marked, and those whose raw entries are all gone.
    retired: int


def _write_index(partition: str, repository_path: str) -> None:
    """Rewrite ``MEMORY.md`` from what is on disk now. Every path ends here."""
    store.write_index(
        partition,
        render_index(
            store.list_notes(partition), partition=partition, repository_path=repository_path
        ),
    )


def _prepare(
    partition: str,
) -> tuple[Sequence[Note], Sequence[RetiredNote], int, Sequence[StoredRawEntry]]:
    """Retire the marked notes and the notes whose sources are gone, then say which
    entries are new."""
    notes, retired, marked = retire_marked(
        partition, store.list_notes(partition), store.read_retired(partition)
    )
    notes, retired, sourceless = retire_sourceless(partition, notes, retired)
    return notes, retired, marked + sourceless, undistilled(partition, notes, retired)


def _open_notes(
    partition: str,
    *,
    notes: Sequence[Note],
    retired: Sequence[RetiredNote],
    entries: Sequence[StoredRawEntry],
    repository_path: str,
    retired_count: int,
) -> DistilResult:
    """One note per entry, then the index.

    There is no merging and no retirement by contradiction here, because both are
    judgements about meaning; the agent a person hands the partition to makes them.
    """
    taken = {n.slug for n in notes} | {r.slug for r in retired if r.slug}
    opened = 0
    for entry in entries:
        raw = entry.entry
        slug = unique_slug(raw.title or entry.entry_id, taken)
        taken.add(slug)
        stamp = now()
        store.write_note(
            Note(
                slug=slug,
                title=raw.title or slug,
                description=" ".join(raw.description.split()),
                type=note_type(raw.type),
                body=raw.body,
                partition=partition,
                origins=(entry.origin,),
                created_at=stamp,
                updated_at=stamp,
                search_terms=raw.search_terms,
            )
        )
        opened += 1
    _write_index(partition, repository_path)
    logger.info(
        "memory.distil.pass; partition=%s opened=%d retired=%d", partition, opened, retired_count
    )
    return DistilResult(partition=partition, opened=opened, retired=retired_count)


async def distil_partition(partition: str, *, repository_path: str = "") -> DistilResult:
    """Distil one partition's new raw entries into its notes, then index it.

    With no new entries it writes the index and nothing else, which is what makes a
    sweep over an idle vault free and what the acceptance scenario's "a second pass
    over unchanged sources reinstates nothing" rests on.
    """
    # Disk work (parsing every note and raw entry, writing the retirements): off the loop.
    notes, retired, retired_count, entries = await asyncio.to_thread(_prepare, partition)
    return await asyncio.to_thread(
        _open_notes,
        partition,
        notes=notes,
        retired=retired,
        entries=entries,
        repository_path=repository_path,
        retired_count=retired_count,
    )


__all__ = [
    "SOURCES_GONE_REASON",
    "DistilResult",
    "distil_partition",
    "has_distil_work",
    "retire_marked",
    "retire_sourceless",
    "undistilled",
]
