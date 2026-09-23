"""Carrying out a distil pass's plan: notes written, notes retired (see "Record
retirements so they stick").

The plan :mod:`~coffer.application.memory.distil_plan` built says what should
happen; this is where it happens, in an order chosen so that no failure can
leave the partition worse than not running would have.

**Notes first, retirements second.** A retirement whose replacement the writing
stage could not produce is skipped and the note stays: taking a subject out of
the partition and putting nothing back is the one outcome worse than an
unrefreshed note.

**A retirement is two halves and they never come apart.** The note's file
leaves ``notes/`` and a record goes into ``RETIRED.md`` in the same loop. The
material the note was built from still sits in the agent's own memory, so a
deletion with no record is undone by the next aggregation — in a store whose
sources live outside it, that file *is* the deletion.

**An entry the pass kept nothing from is recorded too.** "Keep distil out of the raw
directory" forbids deleting it from ``.raw/``, so without a record it would be routed
again on every pass for the rest of the vault's life. Such a record carries the entry in
``entry_ids`` and leaves ``slug`` empty: no note ever existed, and naming one would
print a path into ``RETIRED.md`` that never did either.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from coffer.application.engine_ports import LlmCompletionPort
from coffer.application.engine_timeout import DEFAULT_MODEL_TIMEOUT_S
from coffer.application.memory import distil_write as writing
from coffer.application.memory.distil_plan import Counts, Plan, Target, now
from coffer.domain.memory.note import Note
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory import store

logger = logging.getLogger(__name__)

#: What a ``RETIRED.md`` record says when it is an entry the pass kept nothing
#: from rather than a note it removed. The prefix is what tells a human reading
#: the file which of the two they are looking at.
DROPPED_REASON_PREFIX = "Kept nothing from this entry: "


def assemble(target: Target, written: writing.WrittenNote, partition: str) -> Note:
    """One rewritten note: the model's three fields, Coffer's bookkeeping.

    Provenance accumulates rather than being replaced (see "Record provenance and merge
    by meaning") — the note is what answers "which of my agents already knows this", and
    a merge that forgot its earlier origins would erase half the answer. So does
    ``created_at``: a note is rewritten, not replaced, so only ``updated_at`` moves.
    """
    existing = target.existing
    origins = list(existing.origins) if existing else []
    seen = {o.key for o in origins}
    terms = list(existing.search_terms) if existing else []
    for entry in target.entries:
        origin = entry.origin
        if origin.key not in seen:
            origins.append(origin)
            seen.add(origin.key)
        terms.extend(t for t in entry.entry.search_terms if t and t not in terms)
    stamp = now()
    return Note(
        slug=target.slug,
        title=written.title,
        description=written.description,
        type=target.type,
        body=written.body,
        partition=partition,
        origins=tuple(origins),
        created_at=(existing.created_at if existing and existing.created_at else stamp),
        updated_at=stamp,
        search_terms=tuple(terms),
    )


async def _write_targets(
    partition: str,
    plan: Plan,
    counts: Counts,
    *,
    model: Any,
    completion: LlmCompletionPort,
    credential_resolver: Callable[[str], str],
    timeout: float = DEFAULT_MODEL_TIMEOUT_S,
) -> set[str]:
    """Stage two, once per touched note. Returns the slugs actually written."""
    written: set[str] = set()
    for slug in sorted(plan.targets):
        target = plan.targets[slug]
        result = await writing.rewrite_note(
            target.entries,
            existing=target.existing,
            partition=partition,
            model=model,
            completion=completion,
            credential_resolver=credential_resolver,
            timeout=timeout,
        )
        if result is None:
            # Degrades to nothing (see "Record what each distil pass did"): the entries
            # routed here are still in ``.raw/`` and still unaccounted for, so the next
            # pass sees them again.
            logger.warning("memory.distil.note_unwritten; partition=%s slug=%s", partition, slug)
            continue
        store.write_note(assemble(target, result, partition))
        written.add(slug)
        if target.existing is None:
            counts.opened += 1
        else:
            counts.merged += len(target.entries)
        logger.info(
            "memory.distil.note_written; partition=%s slug=%s entries=%d new=%s",
            partition,
            slug,
            len(target.entries),
            target.existing is None,
        )
    return written


def _retirement_records(
    partition: str, plan: Plan, counts: Counts, written: set[str]
) -> list[RetiredNote]:
    """Delete each retired note's file and build its record — both halves.

    A deletion without a record is undone by the next pass, which re-reads the same
    unchanged raw entry (see "Record retirements so they stick"), so the two happen in
    one loop.
    """
    records: list[RetiredNote] = []
    for slug in sorted(plan.retirements):
        record = plan.retirements[slug]
        if record.replaced_by and record.replaced_by not in written:
            logger.warning(
                "memory.distil.retirement_skipped; partition=%s slug=%s", partition, slug
            )
            continue
        store.delete_note(partition, slug)
        records.append(record)
        counts.retired += 1
        logger.info(
            "memory.distil.retired; partition=%s slug=%s replaced_by=%s",
            partition,
            slug,
            record.replaced_by,
        )
    return records


def _drop_records(partition: str, plan: Plan, counts: Counts) -> list[RetiredNote]:
    """One record per entry the pass kept nothing from.

    "Keep distil out of the raw directory" forbids deleting the entry, so without this
    the same entry would be routed on every pass for the rest of the vault's life. What
    excludes it is ``entry_ids``; ``slug`` stays **empty**, because no note was ever
    written and naming one would print a path into ``RETIRED.md`` that has never
    existed. The title joins the retired subjects the next routing prompt must not
    re-open.
    """
    stamp = now()
    records: list[RetiredNote] = []
    for entry, reason in plan.drops:
        records.append(
            RetiredNote(
                slug="",
                title=entry.entry.title or entry.entry_id,
                reason=DROPPED_REASON_PREFIX + (reason or "nothing worth carrying forward."),
                replaced_by="",
                retired_at=stamp,
                entry_ids=(entry.entry_id,),
            )
        )
        counts.dropped += 1
        logger.info("memory.distil.dropped; partition=%s entry=%s", partition, entry.entry_id)
    return records


async def carry_out(
    partition: str,
    plan: Plan,
    *,
    retired: Sequence[RetiredNote],
    model: Any,
    completion: LlmCompletionPort,
    credential_resolver: Callable[[str], str],
    timeout: float = DEFAULT_MODEL_TIMEOUT_S,
) -> Counts:
    """Write the notes, then retire what they replaced, then record all of it."""
    counts = Counts()
    written = await _write_targets(
        partition,
        plan,
        counts,
        model=model,
        completion=completion,
        credential_resolver=credential_resolver,
        timeout=timeout,
    )
    records = _retirement_records(partition, plan, counts, written)
    records.extend(_drop_records(partition, plan, counts))
    if records:
        # ``write_retired`` rewrites the whole file, so what was already there
        # goes back down with it — a lossy round-trip here is a note re-opened
        # on the next pass, which is the failure "Record retirements so they stick"
        # exists to prevent.
        store.write_retired(partition, [*retired, *records])
    return counts


__all__ = [
    "DROPPED_REASON_PREFIX",
    "assemble",
    "carry_out",
]
