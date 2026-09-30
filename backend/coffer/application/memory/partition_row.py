"""A ``memory`` Resource row as the memory layer reads it.

The partition's config schema, the summary the management surface lists, and
the pure conversions between a row, the aggregation pass's ``Placement`` and
that summary. Split out of ``service.py`` so the service holds only the passes
and the reads; ``service`` re-exports the two public types.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from coffer.application.memory.aggregate import Placement
from coffer.application.memory.distil import undistilled
from coffer.domain.memory.partition import GLOBAL_PARTITION
from coffer.domain.resource import Resource
from coffer.infrastructure.memory import paths, store


class MemoryPartitionConfig(BaseModel):
    """``Resource.config`` payload when ``kind == 'memory'``.

    Two fields, because a partition is keyed on a **repository** and a
    repository is two things: an identity that two clones agree on, and a place
    on this disk.

    ``repository_key`` is what a working directory is resolved to —
    ``remote:<host>/<path>`` when the repository has an ``origin``, so the main
    checkout, a worktree and a second clone all land here, and ``path:<abs>``
    when it has none. ``repository_path`` is the absolute root, which "Identify a partition by
    its repository" requires be recorded on the Resource and which ``context.py`` matches a
    session's ``cwd`` against. Both are empty for ``global``, which is not a
    repository.

    This replaces a single ``project_root``, whose value was the raw working
    directory an entry happened to be learned in — the key that split a
    worktree from its own checkout and made six dated scratch folders into six
    permanent partitions (see "Create no partition for a non-repository directory").
    """

    model_config = ConfigDict(extra="forbid")

    repository_key: str = ""
    repository_path: str = ""


@dataclass(frozen=True)
class PartitionSummary:
    """One partition as the management surface lists it (see "Present a partition as its
    memories").

    ``unresolvable`` is computed here rather than stored, and it is the whole of "Report
    unresolvable partitions": a partition whose repository is no longer on this disk can
    never be resolved from any working directory again, so it is delivered to nobody. It
    is **surfaced rather than hidden**, because only the developer can decide whether
    that repository is coming back — an orphaned partition on the maintainer's live
    vault simply sat there, undeliverable and unmentioned. A partition that carries no
    ``repository_path`` at all is unresolvable for the same reason, and for one more: it
    predates repository identity, so nothing will ever match it either.
    """

    #: The partition's identity — what a surface addresses it by, and what the
    #: distil sweep and Update memory both claim, so neither can be aimed
    #: at a different partition by a label that moved in between.
    uid: str
    name: str
    repository_key: str
    repository_path: str
    note_count: int
    unresolvable: bool
    #: The display title a person chose (spec resource-framework "Carry an optional
    #: editable title on the kinds that have one"); ``None`` when unset, and a surface shows
    #: the name in its place.
    title: str | None = None
    #: When a distil pass last finished over this partition, or ``None`` if none
    #: has — what the table's Distil column and the header's "distilled 2 h ago"
    #: read (spec memory "Present a partition as its memories").
    distilled_at: datetime | None = None
    #: One memory to show the partition by: the most recently updated one's line.
    sample: str | None = None
    #: The agents (resource names) this partition's memory came from.
    sources: tuple[str, ...] = ()
    #: Raw entries read from the agents that no distil pass has decided on yet,
    #: and which agents they came from — "3 entries read from Codex, waiting to
    #: distil".
    waiting_entries: int = 0
    waiting_agents: tuple[str, ...] = ()


def placement_of(row: Resource) -> Placement:
    """One ``memory`` Resource row as the pass's own value object."""
    return Placement(
        name=row.name,
        repository_key=str(row.config.get("repository_key", "") or ""),
        repository_path=str(row.config.get("repository_path", "") or ""),
    )


def config_of(placement: Placement) -> dict[str, str]:
    return {
        "repository_key": placement.repository_key,
        "repository_path": placement.repository_path,
    }


def summary_of(row: Resource, placement: Placement) -> PartitionSummary:
    notes = store.list_notes(row.name)
    waiting = undistilled(row.name, notes, store.read_retired(row.name))
    # The agents behind the partition: whoever a memory was learned from, and
    # whoever left an entry no pass has distilled yet.
    agents = {o.agent for note in notes for o in note.origins} | {e.agent for e in waiting}
    newest = max(notes, key=lambda n: n.updated_at, default=None)
    return PartitionSummary(
        uid=row.uid,
        name=row.name,
        title=row.title,
        repository_key=placement.repository_key,
        repository_path=placement.repository_path,
        note_count=len(notes),
        unresolvable=is_unresolvable(placement),
        distilled_at=_distilled_at(row.name),
        sample=(newest.description or newest.title) if newest is not None else None,
        sources=tuple(sorted(a for a in agents if a)),
        waiting_entries=len(waiting),
        waiting_agents=tuple(sorted({e.agent for e in waiting if e.agent})),
    )


def _distilled_at(name: str) -> datetime | None:
    """When a distil pass last finished here: every pass, mechanical or not,
    ends by rewriting the index, and nothing else writes it."""
    path = paths.index_path(name)
    if not path.is_file():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def is_unresolvable(placement: Placement) -> bool:
    """Can any working directory still resolve to this partition?

    ``global`` always can — it is delivered wherever the developer is working,
    which is what it is for. Every other partition needs a repository path that
    is still a directory on this disk.
    """
    if placement.name == GLOBAL_PARTITION:
        return False
    if not placement.repository_path:
        return True
    return not pathlib.Path(placement.repository_path).is_dir()
