"""The distil pass: raw entries in, Coffer's own notes out (spec memory "Distil
incrementally in two stages").

This is the pass the whole layer exists for. Aggregation reads the agents'
native memories and puts what it found under a partition's ``.raw/``,
verbatim; this turns that into ``notes/`` — one topic per file, in Coffer's
words — and writes the ``MEMORY.md`` a session is actually given.

**The single most important invariant in this module: a retirement is written
to ``RETIRED.md`` *and* the note file is deleted, and ``RETIRED.md`` is part of
the next pass's input (see "Record retirements so they stick").** Every other rule here
can be got wrong and cost one pass. This one, got wrong, costs every pass forever: the
material a note was built from still lives in the agent's own memory, outside anything
Coffer controls, so the next aggregation reads it again and the next distil pass
re-opens the note this one removed. In a store whose sources live outside it, **an
unrecorded deletion is undone**. ``RETIRED.md`` is not a bin, it is the mechanism, and
every routing prompt is handed its titles with an instruction not to re-open them.

**Two stages, so no single request carries the partition's bodies.** Routing
(:mod:`~coffer.application.memory.distil_routing`) gets this round's new
entries, the existing notes as **index lines only**, and the retirement
record; it returns one of four actions per entry. Writing
(:mod:`~coffer.application.memory.distil_write`) then gets **one** note's body
plus the entries routed to it, one request per note actually touched. A
partition of a hundred notes that gained three entries costs one routing
request over a hundred index lines and at most three small writing requests —
never a hundred bodies. :mod:`~coffer.application.memory.distil_plan` folds
the routing answers into a plan and
:mod:`~coffer.application.memory.distil_apply` carries it out.

**``.raw/`` is never written here (see "Keep distil out of the raw directory").** Not
one call: the pass uses ``store.list_raw_entries`` and nothing else from the store's raw
half, which makes the rule checkable by reading the call sites rather than by trusting a
comment. That separation is what lets a bad distillation be re-run without going back to
the agents.

**``MEMORY.md`` is always written, on every path.** Even when nothing changed, even when
no model was available, even when every model call failed. A pass must never leave a
partition without an index, because the index *is* the delivery (see "Deliver the index
and the notes path at session start") — a partition with notes and no index delivers
nothing.

**No internal connection, no model call — structurally (see "Distil mechanically with no
internal connection").** The mechanical path is :func:`_distil_mechanically`, a
**synchronous** function handed no completion port and no model selector. It cannot call
a model because it has nothing to call one with, rather than because it was careful not
to. Each new entry becomes a note of its own, carrying the source's own title,
description, text, type and search terms, and the index is rendered from their
frontmatter. Thinner, not absent.

**Malformed model output degrades to nothing, never to an exception
(see "Record what each distil pass did").** An unknown slug, a non-JSON answer, an
action naming an entry not in the batch, a note the writing stage could not produce:
each is logged and skipped, and the entries involved stay in ``.raw/`` for the next pass
to see again. This keeps the organise pass's discipline, which was good, and it is why a
pass against a degraded model is merely useless rather than destructive.

**Which entries are new.** An entry is undistilled when its ``entry_id``
appears neither in any note's ``origins`` nor in any ``RETIRED.md`` record's
``entry_ids``. Both halves matter. Without the first, every pass re-routes the
whole partition. Without the second, an entry the pass deliberately kept
nothing from would be re-offered forever, since a dropped entry stays in
``.raw/`` ("Keep distil out of the raw directory" forbids deleting it). So a drop is
recorded as a retirement record naming the **entry ids** it excludes — the identity of
what is being left out — and that record's title joins the retired subjects the next
routing prompt must not re-open.

**A note whose raw entries are all gone is retired (see "Retire a note whose raw
entries are all gone").** Aggregation deletes a raw entry when its source stops
producing it — the agent deleted the fact, or placement now files it into another
partition — and a note is only derived from what ``.raw/`` holds. So every pass,
on every path, first retires each note none of whose origins is still in
``.raw/``, and records it in ``RETIRED.md`` with ``sources_gone`` set. That is
not a judgement about meaning, so the mechanical path does it too, and it is
not an exclusion either: the record names no entry ids and its title is not
handed to routing, so material that comes back is distilled afresh. A note
that still has one origin standing is left alone.

A retired *note*'s own origins go on its record the same way. Nothing else
accounts for them once the note file is gone, so leaving them off would send
them back through routing a round later only to be dropped — charged to the
model twice to reach the answer this pass already had. Both cases therefore
converge in one pass.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from coffer.application.engine_ports import LlmCompletionPort, ModelSelectorPort
from coffer.application.engine_timeout import TimeoutReader, resolve_timeout
from coffer.application.memory import distil_apply as applying
from coffer.application.memory import distil_plan as planning
from coffer.application.memory import distil_routing as routing
from coffer.application.memory.distil_sources import (
    SOURCES_GONE_REASON,
    has_distil_work,
    retire_sourceless,
    undistilled,
)
from coffer.application.memory.index import render_index
from coffer.domain.memory.note import Note
from coffer.domain.memory.retired import RetiredNote
from coffer.domain.memory.trigger import KIND_BLOCK, TriggerProposal
from coffer.infrastructure.memory import store
from coffer.infrastructure.memory.raw_store import StoredRawEntry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DistilResult:
    """What one distil pass over one partition did (see "Record what each distil pass
    did").

    Enough for a developer to answer why a note reads the way it does: the
    per-action detail goes to the log, and these are the counts the audit
    event and the surfaces carry.
    """

    partition: str
    #: Raw entries folded into a note that already existed.
    merged: int
    #: Notes created for a subject not yet covered.
    opened: int
    #: Notes a later entry contradicted, or whose raw entries are all gone —
    #: removed from ``notes/`` and recorded in ``RETIRED.md``.
    retired: int
    #: Entries the pass kept nothing from.
    dropped: int
    #: Whether an internal connection was configured at all. False means the
    #: mechanical path ran (see "Distil mechanically with no internal connection") — not
    #: that a model was asked and declined.
    model_used: bool
    #: Triggers the writing stage proposed, unarmed (spec memory "Keep triggers
    #: in the vault, armed only by a person").
    proposals: tuple[TriggerProposal, ...] = ()


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
    """Retire the notes whose sources are gone, then say which entries are new."""
    notes, retired, sourceless = retire_sourceless(
        partition, store.list_notes(partition), store.read_retired(partition)
    )
    return notes, retired, sourceless, undistilled(partition, notes, retired)


def _distil_mechanically(
    partition: str,
    *,
    notes: Sequence[Note],
    retired: Sequence[RetiredNote],
    entries: Sequence[StoredRawEntry],
    repository_path: str,
    retired_count: int = 0,
) -> DistilResult:
    """Distil without a model: one note per entry, then the index (see "Distil
    mechanically with no internal connection").

    Synchronous, and handed neither a completion port nor a model selector —
    which is how "MUST NOT call a model on any path" is held structurally
    rather than by a condition somebody could later invert.

    There is no merging and no retirement by contradiction here, because both
    are judgements about meaning and nothing mechanical can make them. The one
    retirement that is not a judgement — a note whose sources are all gone —
    has already happened by the time this runs, and ``retired_count`` carries
    it. What there *is* is a real partition: notes at real paths, an index over
    them, and a delivery. Thinner than the model's, not absent.
    """
    taken = {n.slug for n in notes} | {r.slug for r in retired if r.slug}
    opened = 0
    for entry in entries:
        raw = entry.entry
        slug = planning.unique_slug(raw.title or entry.entry_id, taken)
        taken.add(slug)
        stamp = planning.now()
        store.write_note(
            Note(
                slug=slug,
                title=raw.title or slug,
                description=" ".join(raw.description.split()),
                type=planning.note_type(raw.type),
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
    logger.info("memory.distil.mechanical_pass; partition=%s opened=%d", partition, opened)
    return DistilResult(
        partition=partition,
        merged=0,
        opened=opened,
        retired=retired_count,
        dropped=0,
        model_used=False,
    )


def _unbound_secret(ref: str) -> str:
    """Stand-in for a resolver the composition root did not supply."""
    return ref


async def distil_partition(
    partition: str,
    *,
    completion: LlmCompletionPort | None,
    model_selector: ModelSelectorPort | None,
    repository_path: str = "",
    secret_resolver: Callable[[str], str] | None = None,
    max_entries_per_chunk: int = routing.DEFAULT_MAX_ENTRIES_PER_CHUNK,
    read_timeout: TimeoutReader | None = None,
) -> DistilResult:
    """Distil one partition's new raw entries into its notes, then index it.

    With no internal connection — no selector, no model on it, or no
    completion port — this hands off to :func:`_distil_mechanically` (see "Distil
    mechanically with no internal connection").
    With no new entries it writes the index and nothing else, which is what
    makes a sweep over an idle vault free and what the acceptance scenario's
    "a second pass over unchanged sources reinstates nothing" rests on.

    ``secret_resolver`` is optional because the composition root may bind
    one into the completion adapter it passes instead; when neither happens
    the ref travels unresolved, the completion fails, and the pass degrades to
    having written nothing but the index.

    ``read_timeout`` is read once per pass, not once per request: a pass is
    minutes long and every call in it should be judged by the same bound, so a
    settings change mid-pass takes effect from the next one. ``None`` is the
    built-in default (spec internal-engine "Carry the bound on one model call").
    """
    # Disk work (parsing every note and raw entry, writing the retirements): off the loop.
    notes, retired, sourceless, entries = await asyncio.to_thread(_prepare, partition)

    model = await model_selector.get_default() if model_selector is not None else None
    if model is None or completion is None:
        return await asyncio.to_thread(
            _distil_mechanically,
            partition,
            notes=notes,
            retired=retired,
            entries=entries,
            repository_path=repository_path,
            retired_count=sourceless,
        )

    if not entries:
        _write_index(partition, repository_path)
        return DistilResult(
            partition=partition,
            merged=0,
            opened=0,
            retired=sourceless,
            dropped=0,
            model_used=True,
        )

    resolver = secret_resolver if secret_resolver is not None else _unbound_secret
    timeout = await resolve_timeout(read_timeout)
    plan = await planning.build_plan(
        partition,
        entries,
        notes=notes,
        retired=retired,
        model=model,
        completion=completion,
        secret_resolver=resolver,
        timeout=timeout,
        chunk_size=max_entries_per_chunk,
    )
    counts = await applying.carry_out(
        partition,
        plan,
        retired=retired,
        model=model,
        completion=completion,
        secret_resolver=resolver,
        timeout=timeout,
    )
    _write_index(partition, repository_path)
    logger.info(
        "memory.distil.pass; partition=%s entries=%d merged=%d opened=%d retired=%d dropped=%d",
        partition,
        len(entries),
        counts.merged,
        counts.opened,
        counts.retired + sourceless,
        counts.dropped,
    )
    return DistilResult(
        partition=partition,
        merged=counts.merged,
        opened=counts.opened,
        retired=counts.retired + sourceless,
        dropped=counts.dropped,
        model_used=True,
        proposals=tuple(
            TriggerProposal(slug=slug, kind=KIND_BLOCK, command=command, unless=unless)
            for slug, command, unless in counts.proposals
        ),
    )


__all__ = [
    "SOURCES_GONE_REASON",
    "DistilResult",
    "distil_partition",
    "has_distil_work",
    "retire_sourceless",
    "undistilled",
]
