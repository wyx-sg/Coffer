"""Which raw entries a distil pass still owes, which notes an agent has marked, and
which have lost their sources.

Split out of ``distil.py``, which runs the pass. Everything here reads ``.raw/`` and
``notes/`` and decides what a pass has to do (see "Distil each raw entry into a note mechanically",
"Retire a note an agent marked retired" and "Retire a note whose raw entries are all
gone"); only :func:`retire_marked` and :func:`retire_sourceless` write, and they write
the retirement, never ``.raw/``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from coffer.application.memory.note_naming import now
from coffer.domain.memory.note import Note
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory import raw_store, store
from coffer.infrastructure.memory.raw_store import StoredRawEntry

logger = logging.getLogger(__name__)


def undistilled(
    partition: str, notes: Sequence[Note], retired: Sequence[RetiredNote]
) -> tuple[StoredRawEntry, ...]:
    """The entries under ``.raw/`` no pass has yet decided anything about.

    See the module docstring's "Which entries are new": an entry is accounted
    for once its id is in some note's provenance, or once a ``RETIRED.md``
    record names it. Reads ``.raw/`` and writes nothing (see "Leave the raw directory to
    aggregation").

    A retirement record names its entries in ``entry_ids`` whether it retired
    a note or merely kept nothing from what it read. That is what makes both
    cases converge in one pass: a retired note's own entries are excluded the
    moment the note leaves, rather than surfacing as undistilled again a round
    later.
    """
    accounted = {o.key for note in notes for o in note.origins}
    accounted |= {entry_id for record in retired for entry_id in record.entry_ids}
    return tuple(e for e in raw_store.list_raw_entries(partition) if e.entry_id not in accounted)


def has_distil_work(partition: str) -> bool:
    """Whether a pass over ``partition`` has anything to do besides rewrite the index.

    What "Update memory in one action" distils after aggregating: a note an agent has
    marked retired, raw entries no pass has decided anything about, or a note none of whose raw
    entries is left (its
    source was deleted — it would otherwise stay in delivery until the next sweep).
    A partition this answers False for would get nothing from a pass but a rewritten
    index. Reads only, like :func:`undistilled`.
    """
    notes = store.list_notes(partition)
    if any(note.retired for note in notes):
        return True
    entries = raw_store.list_raw_entries(partition)
    present = {e.entry_id for e in entries}
    if any(note.origins and not any(o.key in present for o in note.origins) for note in notes):
        return True
    accounted = {o.key for note in notes for o in note.origins}
    accounted |= {i for record in store.read_retired(partition) for i in record.entry_ids}
    return any(e.entry_id not in accounted for e in entries)


SOURCES_GONE_REASON = (
    "Every raw entry this note was built from is gone from this partition's `.raw/` — "
    "the agent no longer holds it, or it is now filed into another partition."
)


def retire_marked(
    partition: str, notes: Sequence[Note], retired: Sequence[RetiredNote]
) -> tuple[tuple[Note, ...], tuple[RetiredNote, ...], int]:
    """Retire every note whose frontmatter carries ``retired: <reason>``.

    An agent tidying the partition cannot compute raw entry ids, and a note it
    simply deleted would come back, because its origins would be undistilled again
    (see "Record retirements so they stick"). So it marks the note, and this
    records the retirement — the note's slug, title, reason, ``replaced_by`` and
    its origin keys as ``entry_ids`` — rewrites ``RETIRED.md``, and then deletes
    the file. Record first, file second: a crash between the two leaves the note
    standing and recorded, never deleted and forgotten.

    Returns the notes still standing, the full retirement list and how many were
    retired. A merge needs no marker: the survivor carries the merged note's
    origins, which already account for those entries.
    """
    marked = [note for note in notes if note.retired]
    if not marked:
        return tuple(notes), tuple(retired), 0
    stamp = now()
    records = [
        RetiredNote(
            slug=note.slug,
            title=note.title or note.slug,
            reason=note.retired,
            replaced_by=note.replaced_by,
            retired_at=stamp,
            entry_ids=tuple(o.key for o in note.origins),
        )
        for note in marked
    ]
    every = (*retired, *records)
    store.write_retired(partition, every)
    for note in marked:
        store.delete_note(partition, note.slug)
        logger.info("memory.distil.marked_retired; partition=%s slug=%s", partition, note.slug)
    standing = tuple(note for note in notes if not note.retired)
    return standing, every, len(records)


def retire_sourceless(
    partition: str, notes: Sequence[Note], retired: Sequence[RetiredNote]
) -> tuple[tuple[Note, ...], tuple[RetiredNote, ...], int]:
    """Retire every note none of whose origins is left in ``.raw/``.

    Returns the notes still standing, the full retirement list (what was
    already recorded plus the new records) and how many were retired. Both
    halves of each retirement happen here — the file leaves ``notes/`` and
    ``RETIRED.md`` is rewritten — so the pass that follows starts from a
    partition that already agrees with its sources (see "Retire a note whose
    raw entries are all gone"). A note with no origins at all is left alone:
    there is no provenance to judge it by.
    """
    present = {e.entry_id for e in raw_store.list_raw_entries(partition)}
    standing: list[Note] = []
    records: list[RetiredNote] = []
    for note in notes:
        if not note.origins or any(o.key in present for o in note.origins):
            standing.append(note)
            continue
        store.delete_note(partition, note.slug)
        records.append(
            RetiredNote(
                slug=note.slug,
                title=note.title,
                reason=SOURCES_GONE_REASON,
                retired_at=now(),
                sources_gone=True,
            )
        )
        logger.info("memory.distil.sources_gone; partition=%s slug=%s", partition, note.slug)
    if not records:
        return tuple(notes), tuple(retired), 0
    every = (*retired, *records)
    store.write_retired(partition, every)
    return tuple(standing), every, len(records)


__all__ = [
    "SOURCES_GONE_REASON",
    "has_distil_work",
    "retire_marked",
    "retire_sourceless",
    "undistilled",
]
