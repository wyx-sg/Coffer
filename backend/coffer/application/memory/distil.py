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

A retired *note*'s own origins go on its record the same way. Nothing else
accounts for them once the note file is gone, so leaving them off would send
them back through routing a round later only to be dropped — charged to the
model twice to reach the answer this pass already had. Both cases therefore
converge in one pass.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from coffer.application.engine_ports import LlmCompletionPort, ModelSelectorPort
from coffer.application.engine_timeout import TimeoutReader, resolve_timeout
from coffer.application.memory import distil_apply as applying
from coffer.application.memory import distil_plan as planning
from coffer.application.memory import distil_routing as routing
from coffer.application.memory.index import render_index
from coffer.domain.memory.note import Note
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory import raw_store, store
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
    #: Notes a later entry contradicted — removed from ``notes/`` and recorded
    #: in ``RETIRED.md``.
    retired: int
    #: Entries the pass kept nothing from.
    dropped: int
    #: Whether an internal connection was configured at all. False means the
    #: mechanical path ran (see "Distil mechanically with no internal connection") — not
    #: that a model was asked and declined.
    model_used: bool


def undistilled(
    partition: str, notes: Sequence[Note], retired: Sequence[RetiredNote]
) -> tuple[StoredRawEntry, ...]:
    """The entries under ``.raw/`` no pass has yet decided anything about.

    See the module docstring's "Which entries are new": an entry is accounted
    for once its id is in some note's provenance, or once a ``RETIRED.md``
    record names it. Reads ``.raw/`` and writes nothing (see "Keep distil out of the raw
    directory").

    A retirement record names its entries in ``entry_ids`` whether it retired
    a note or merely kept nothing from what it read. That is what makes both
    cases converge in one pass: a retired note's own entries are excluded the
    moment the note leaves, rather than surfacing as undistilled again and
    having to be re-judged (and re-charged to the model) a round later.
    """
    accounted = {o.key for note in notes for o in note.origins}
    accounted |= {entry_id for record in retired for entry_id in record.entry_ids}
    return tuple(e for e in raw_store.list_raw_entries(partition) if e.entry_id not in accounted)


def _write_index(partition: str, repository_path: str) -> None:
    """Rewrite ``MEMORY.md`` from what is on disk now. Every path ends here."""
    store.write_index(
        partition,
        render_index(
            store.list_notes(partition), partition=partition, repository_path=repository_path
        ),
    )


def _distil_mechanically(
    partition: str,
    *,
    notes: Sequence[Note],
    retired: Sequence[RetiredNote],
    entries: Sequence[StoredRawEntry],
    repository_path: str,
) -> DistilResult:
    """Distil without a model: one note per entry, then the index (see "Distil
    mechanically with no internal connection").

    Synchronous, and handed neither a completion port nor a model selector —
    which is how "MUST NOT call a model on any path" is held structurally
    rather than by a condition somebody could later invert.

    There is no merging and no retirement here, because both are judgements
    about meaning and nothing mechanical can make them. What there *is* is a
    real partition: notes at real paths, an index over them, and a delivery.
    Thinner than the model's, not absent.
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
        partition=partition, merged=0, opened=opened, retired=0, dropped=0, model_used=False
    )


def _unbound_credential(ref: str) -> str:
    """Stand-in for a resolver the composition root did not supply."""
    return ref


async def distil_partition(
    partition: str,
    *,
    completion: LlmCompletionPort | None,
    model_selector: ModelSelectorPort | None,
    repository_path: str = "",
    credential_resolver: Callable[[str], str] | None = None,
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

    ``credential_resolver`` is optional because the composition root may bind
    one into the completion adapter it passes instead; when neither happens
    the ref travels unresolved, the completion fails, and the pass degrades to
    having written nothing but the index.

    ``read_timeout`` is read once per pass, not once per request: a pass is
    minutes long and every call in it should be judged by the same bound, so a
    settings change mid-pass takes effect from the next one. ``None`` is the
    built-in default (spec internal-engine "Carry the bound on one model call").
    """
    notes = store.list_notes(partition)
    retired = store.read_retired(partition)
    entries = undistilled(partition, notes, retired)

    model = await model_selector.get_default() if model_selector is not None else None
    if model is None or completion is None:
        return _distil_mechanically(
            partition,
            notes=notes,
            retired=retired,
            entries=entries,
            repository_path=repository_path,
        )

    if not entries:
        _write_index(partition, repository_path)
        return DistilResult(
            partition=partition, merged=0, opened=0, retired=0, dropped=0, model_used=True
        )

    resolver = credential_resolver if credential_resolver is not None else _unbound_credential
    timeout = await resolve_timeout(read_timeout)
    plan = await planning.build_plan(
        partition,
        entries,
        notes=notes,
        retired=retired,
        model=model,
        completion=completion,
        credential_resolver=resolver,
        timeout=timeout,
        chunk_size=max_entries_per_chunk,
    )
    counts = await applying.carry_out(
        partition,
        plan,
        retired=retired,
        model=model,
        completion=completion,
        credential_resolver=resolver,
        timeout=timeout,
    )
    _write_index(partition, repository_path)
    logger.info(
        "memory.distil.pass; partition=%s entries=%d merged=%d opened=%d retired=%d dropped=%d",
        partition,
        len(entries),
        counts.merged,
        counts.opened,
        counts.retired,
        counts.dropped,
    )
    return DistilResult(
        partition=partition,
        merged=counts.merged,
        opened=counts.opened,
        retired=counts.retired,
        dropped=counts.dropped,
        model_used=True,
    )


__all__ = ["DistilResult", "distil_partition", "undistilled"]
