"""What the distil pass decided, and the carrying out of it (spec memory "Distil
incrementally in two stages").

Between the two model-facing stages sits the part that is all Coffer's: the
routing answers are folded into a **plan**, and the plan is carried out against
the store. Two rules are enforced here rather than trusted to a prompt, because
a model cannot be relied on to hold them across a chunk boundary.

**A note this pass is writing is not also retired, and one it is retiring is
not also merged into.** Both are reachable once a partition spans several
routing requests, and either leaves a note file contradicting the record of its
own removal.

**A retirement waits for its replacement.** The replacement is written first,
and a retirement whose replacement the writing stage could not produce is
skipped. Retiring a note and putting nothing back is strictly worse than not
running the pass.

Nothing here writes ``.raw/`` (see "Keep distil out of the raw directory"): it reads
entries the caller listed and writes only ``notes/`` and ``RETIRED.md``.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from coffer.application.engine_ports import LlmCompletionPort
from coffer.application.engine_timeout import DEFAULT_MODEL_TIMEOUT_S
from coffer.application.memory import distil_routing as routing
from coffer.domain.memory.note import NOTE_TYPES, TYPE_PROJECT, Note
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory.raw_store import StoredRawEntry

logger = logging.getLogger(__name__)

_SEPARATORS = re.compile(r"[\s_/\\]+")
_DROP = re.compile(r"[^A-Za-z0-9\-一-鿿ぁ-ヿ]")
_DASHES = re.compile(r"-{2,}")
_MAX_SLUG_CHARS = 80


def now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title or "").strip().lower()
    stem = _DASHES.sub("-", _DROP.sub("", _SEPARATORS.sub("-", normalized))).strip("-")
    return (stem or "note")[:_MAX_SLUG_CHARS].strip("-") or "note"


def unique_slug(title: str, taken: set[str]) -> str:
    """A file name for a new note that collides with nothing in the partition.

    ``taken`` carries retired slugs too: re-using the file name of a note this
    partition retired would make ``RETIRED.md`` read as though a live note had
    been removed.
    """
    base = _slugify(title)
    slug = base
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def note_type(*candidates: str) -> str:
    """The first candidate that is a real note type, else ``project``.

    A type decides a note's index group and, for the personal types, which
    partition it belongs in at all, so a stray value from a hand-edited source
    file must not travel into a note.
    """
    for value in candidates:
        if value in NOTE_TYPES:
            return value
    return TYPE_PROJECT


# ----- the plan ---------------------------------------------------------------


@dataclass
class Target:
    """One note the pass will rewrite, and the entries routed into it."""

    slug: str
    existing: Note | None
    title_hint: str
    type: str
    entries: list[StoredRawEntry] = field(default_factory=list)


@dataclass
class Plan:
    """Everything one pass decided, before any of it is on disk."""

    targets: dict[str, Target] = field(default_factory=dict)
    #: Keyed by the slug being retired.
    retirements: dict[str, RetiredNote] = field(default_factory=dict)
    #: ``(entry, reason)`` for every entry the pass kept nothing from.
    drops: list[tuple[StoredRawEntry, str]] = field(default_factory=list)


@dataclass
class Counts:
    merged: int = 0
    opened: int = 0
    retired: int = 0
    dropped: int = 0


def _index_view(live: dict[str, Note], plan: Plan) -> list[routing.IndexEntry]:
    """The index as the next chunk must see it: this pass's edits projected.

    A chunk that opens a note must let the *next* chunk merge into it, and one
    that retires a note must not. Projecting the plan is what makes a partition
    split across several requests behave like one.
    """
    view = [
        routing.IndexEntry(slug=n.slug, title=n.title, description=n.description)
        for slug, n in sorted(live.items())
        if slug not in plan.retirements
    ]
    view.extend(
        routing.IndexEntry(slug=t.slug, title=t.title_hint, description="")
        for t in sorted(plan.targets.values(), key=lambda t: t.slug)
        if t.existing is None
    )
    return view


def _open_target(
    plan: Plan, entry: StoredRawEntry, taken: set[str], *, title: str, type_: str
) -> Target:
    """Start a new note for ``entry``, naming its file now so that a sibling
    entry in the same batch can be routed into it before anything is written."""
    slug = unique_slug(title or entry.entry.title or entry.entry_id, taken)
    taken.add(slug)
    target = Target(
        slug=slug,
        existing=None,
        title_hint=title or entry.entry.title or slug,
        type=note_type(type_, entry.entry.type),
    )
    plan.targets[slug] = target
    return target


def _apply_action(
    action: routing.RouteAction,
    entry: StoredRawEntry,
    *,
    plan: Plan,
    live: dict[str, Note],
    taken: set[str],
    stamp: str,
    placed: dict[str, str],
) -> None:
    """Fold one routed entry into the plan, refusing what would contradict it.

    ``placed`` maps each entry already given a target in this chunk to that
    target's slug, which is what resolves a merge naming a **sibling entry**
    rather than an existing note (``distil_routing.RouteAction.into_entry``).
    """
    if action.action == routing.ACTION_DROP:
        plan.drops.append((entry, action.reason))
        return
    if action.action == routing.ACTION_MERGE:
        slug = action.slug or placed.get(action.into_entry, "")
        if not slug:
            # The sibling it named was dropped, or was itself an unresolved
            # merge. Degrade to nothing: the entry stays undistilled and the
            # next pass offers it again.
            logger.warning(
                "memory.distil.dropped_action; unresolved merge into entry=%s", action.into_entry
            )
            return
        action = replace(action, slug=slug, into_entry="")
        if action.slug in plan.retirements:
            logger.warning("memory.distil.dropped_action; merge into retiring slug=%s", action.slug)
            return
        target = plan.targets.get(action.slug)
        if target is None:
            existing = live.get(action.slug)
            if existing is None:
                logger.warning("memory.distil.dropped_action; merge slug=%s", action.slug)
                return
            target = Target(
                slug=existing.slug,
                existing=existing,
                title_hint=existing.title,
                type=note_type(existing.type, entry.entry.type),
            )
            plan.targets[existing.slug] = target
        target.entries.append(entry)
        placed[entry.entry_id] = target.slug
        return
    if action.action == routing.ACTION_RETIRE:
        doomed = live.get(action.slug)
        if doomed is None or action.slug in plan.targets or action.slug in plan.retirements:
            logger.warning("memory.distil.dropped_action; retire slug=%s", action.slug)
            return
        # The entry that contradicted the note becomes the note replacing it,
        # which is what makes "retired, and here is what replaced it" a record
        # a human can act on rather than a hole in the partition.
        replacement = _open_target(
            plan, entry, taken, title=action.title, type_=action.type or doomed.type
        )
        replacement.entries.append(entry)
        placed[entry.entry_id] = replacement.slug
        plan.retirements[action.slug] = RetiredNote(
            slug=action.slug,
            title=doomed.title or action.slug,
            reason=action.reason,
            replaced_by=replacement.slug,
            retired_at=stamp,
            # The doomed note's own entries go on the record with it. Without
            # them they would come back as undistilled on the next pass —
            # their note is gone, so nothing else accounts for them — and be
            # routed to the model a second time only to be dropped.
            entry_ids=tuple(o.key for o in doomed.origins),
        )
        return
    target = _open_target(plan, entry, taken, title=action.title, type_=action.type)
    target.entries.append(entry)
    placed[entry.entry_id] = target.slug


async def build_plan(
    partition: str,
    entries: Sequence[StoredRawEntry],
    *,
    notes: Sequence[Note],
    retired: Sequence[RetiredNote],
    model: Any,
    completion: LlmCompletionPort,
    credential_resolver: Callable[[str], str],
    timeout: float = DEFAULT_MODEL_TIMEOUT_S,
    chunk_size: int,
) -> Plan:
    """Stage one over every chunk, folded into one plan for the whole pass."""
    plan = Plan()
    live = {n.slug: n for n in notes}
    taken = set(live) | {r.slug for r in retired}
    by_id = {e.entry_id: e for e in entries}
    stamp = now()
    for chunk in routing.chunks(entries, chunk_size):
        # Every retirement is an exclusion the model must see, including the
        # ones this pass has just decided (see "Record retirements so they stick").
        retired_titles = [r.title for r in retired if r.title]
        retired_titles.extend(r.title for r in plan.retirements.values() if r.title)
        actions = await routing.route_chunk(
            chunk,
            index=_index_view(live, plan),
            retired_titles=retired_titles,
            partition=partition,
            model=model,
            completion=completion,
            credential_resolver=credential_resolver,
            timeout=timeout,
        )
        # Two rounds over the chunk: a merge naming a sibling entry can only be
        # resolved once that sibling has a note to join, and the model answers
        # in whatever order it likes.
        placed: dict[str, str] = {}
        deferred = [a for a in actions if a.into_entry]
        for action in [a for a in actions if not a.into_entry] + deferred:
            _apply_action(
                action,
                by_id[action.entry_id],
                plan=plan,
                live=live,
                taken=taken,
                stamp=stamp,
                placed=placed,
            )
    return plan


__all__ = [
    "Counts",
    "Plan",
    "Target",
    "build_plan",
    "note_type",
    "now",
    "unique_slug",
]
