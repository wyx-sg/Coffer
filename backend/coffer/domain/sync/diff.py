"""What one converge round changes, and when that is too much (spec vault-sync).

A round applies a **diff**, not a state. The difference is the whole safety
argument: a wholesale overwrite cannot tell "this vault never had it" from
"some machine deleted it", while a diff against the commit this vault provably
absorbed can only carry a deletion because a machine actually deleted that
document. Paths the diff does not mention are not touched.

Pure domain: computing the diff is git's job and applying it is the application
layer's, but what a change *is*, which area it belongs to, and how much change
is too much to apply unattended all belong here.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Iterable, Sequence
from enum import StrEnum

#: Bundle subdirectory → the area name reported to the user.
_AREA_PREFIXES = (
    ("knowledge/", "knowledge"),
    ("skills/", "skills"),
    ("resources/", "resources"),
    ("state/", "state"),
    ("credentials/", "credentials"),
    ("machines/", "machines"),
)

#: Areas a round never applies to the vault. ``machines/`` is the registry,
#: read straight from the working tree; ``manifest.json`` carries the layout's
#: schema version and says nothing about vault state. The manifest is *read*
#: before a round applies anything — a layout this build does not know is
#: refused (``domain.sync.manifest.refuse_if_too_new``) — but it is never
#: applied, because there is nothing in it to apply.
NON_VAULT_AREAS = frozenset({"machines", "manifest"})

DEFAULT_DELETION_SHARE = 0.2
DEFAULT_DELETION_FLOOR = 20

#: git's hash of the zero-byte blob. Every empty file in every repository has
#: this content id, which makes it the one blob that says nothing about where
#: its bytes came from — so it is never allowed to pair a deletion with an
#: addition (see :func:`losses`).
EMPTY_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


class ChangeStatus(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


def area_of(path: str) -> str:
    """Which area a bundle-relative path belongs to."""
    for prefix, area in _AREA_PREFIXES:
        if path.startswith(prefix):
            return area
    return "manifest"


@dataclasses.dataclass(frozen=True, slots=True)
class DocChange:
    """One document's fate in one diff."""

    path: str
    status: ChangeStatus
    #: git's content id for the bytes this change is *about* — what a deletion
    #: removed, or what an addition or a modification left behind. It comes
    #: straight out of ``git diff --raw``, so it costs nothing to carry and
    #: nothing to compare: identical bytes anywhere in any repository have the
    #: same id, and different bytes do not.
    #:
    #: ``None`` where there is no diff to read it from — a path reconstructed
    #: from the retry set, or a round read back out of the history. A deletion
    #: with no content id can never be shown to be a move, and is therefore
    #: counted as a loss, which is the conservative answer.
    blob: str | None = None

    @property
    def area(self) -> str:
        return area_of(self.path)

    @property
    def touches_vault(self) -> bool:
        return self.area not in NON_VAULT_AREAS


def losses(changes: Iterable[DocChange]) -> tuple[DocChange, ...]:
    """The deletions in a diff that actually lose content: moves excluded.

    A re-layout is the case this exists for. When the knowledge two-lane
    rewrite moved every document from ``knowledge/<c>/<doc>.md`` to
    ``knowledge/<c>/sources/<doc>.md``, the diff carried 56 deletions *and* 56
    additions of the same bytes — and a guard that counted only the deletions
    saw 56 of 58 documents disappearing and held the round, for a round in
    which nothing at all was lost. The vault sat unpublished for a day.

    A deletion is a **move** when the content it removed reappears, in the same
    diff, under another path in the same area. The pairing is on content, never
    on name similarity: git hands us a content id per side of every change, so
    "these are the same bytes" is a fact we can read rather than a resemblance
    we would have to guess at — and a guess that wrongly excuses a deletion
    loses data, while a guess that wrongly holds one costs a click.

    Four edges, decided:

    * **Moved and edited.** The content differs, so it is not a move and the
      deletion counts. A mass relocation that also rewrites its documents is
      held and asked about once, which is the honest answer: nothing here can
      tell it apart from a mass deletion beside a mass addition.
    * **The destination may be an addition or a modification.** A move that
      lands on a path the diff also modified still put the content somewhere,
      and requiring the destination to be brand new would hold a re-layout for
      the few files whose targets already existed. A genuine loss has no
      destination of either sort, so this widens nothing for it.
    * **Two identical documents collapsing into one** are both excused. This is
      set membership, not a one-to-one matching: the guard protects content,
      and the content of a duplicate is still in the vault. Pairing one-to-one
      would also cost a matching pass for no gain in what is protected.
    * **A move that crosses areas is not a move.** The guard's unit is the
      area — its share is measured against that area's own documents — so
      "knowledge lost 56 of 58, and 56 identical files turned up under
      ``credentials/``" is exactly the shape of a botched relocation that did
      damage the knowledge area. Same content, wrong place, still asked about.

    The empty blob is excluded outright. Every empty file has identical
    content, so a single added empty file would otherwise excuse the deletion
    of every empty document in its area — a coincidence by construction rather
    than evidence of a move.

    Linear in the number of changes: one pass to collect the content that
    landed per area, one to test the deletions against it. No bytes are read.
    """
    changes = tuple(changes)
    landed: dict[str, set[str]] = {}
    for change in changes:
        if change.status is not ChangeStatus.DELETED and change.blob:
            landed.setdefault(change.area, set()).add(change.blob)
    return tuple(
        change
        for change in changes
        if change.status is ChangeStatus.DELETED
        and not (
            change.blob
            and change.blob != EMPTY_BLOB
            and change.blob in landed.get(change.area, frozenset())
        )
    )


@dataclasses.dataclass(frozen=True, slots=True)
class DeletionGuard:
    """How much deletion a round may perform without being confirmed.

    Two thresholds, and a round trips the guard when it exceeds **either**.
    The share catches a small vault losing most of itself; the floor catches a
    large one losing a lot in absolute terms while staying under the share.

    The guard runs in both directions. Applied to the incoming diff it bounds
    what a defect — here or on the machine that pushed — can erase from this
    vault. Applied to what this round would publish it bounds the opposite
    failure: a vault that lost its files to a reinstall, a failed restore or a
    stray ``rm -rf`` would otherwise publish that loss as an ordinary deletion
    and carry every other machine down with it.

    It counts **losses**, not deletions (:func:`losses`): a document whose
    content reappears elsewhere in the same diff moved, and a move erases
    nothing. A deletion with no such destination is counted exactly as before,
    which is the whole of what the guard was ever protecting against.
    """

    share: float = DEFAULT_DELETION_SHARE
    floor: int = DEFAULT_DELETION_FLOOR

    def __post_init__(self) -> None:
        if not 0 < self.share <= 1:
            raise ValueError("deletion share must be within (0, 1]")
        if self.floor < 1:
            raise ValueError("deletion floor must be at least 1")

    def breached_areas(
        self, changes: Iterable[DocChange], totals: dict[str, int]
    ) -> list[tuple[str, int, int]]:
        """Areas whose losses exceed the guard, as (area, lost, total).

        ``totals`` is how many documents each area held **before** the change,
        so a share is measured against what is at risk rather than what
        survives. An area missing from ``totals`` is treated as empty, which
        makes any deletion in it a share of 1.0 — correct, because deleting
        from an area this side does not know about is not something to do
        unattended.
        """
        deleted = Counter(c.area for c in losses(c for c in changes if c.touches_vault))
        breached = []
        for area, count in sorted(deleted.items()):
            total = totals.get(area, 0)
            if count >= self.floor or total == 0 or count / total > self.share:
                breached.append((area, count, total))
        return breached


@dataclasses.dataclass(frozen=True, slots=True)
class DiffSummary:
    """A round's diff, grouped for reporting."""

    changes: tuple[DocChange, ...] = ()

    @classmethod
    def of(cls, changes: Sequence[DocChange]) -> DiffSummary:
        return cls(tuple(sorted(changes, key=lambda c: c.path)))

    def __bool__(self) -> bool:
        return bool(self.changes)

    @property
    def vault_changes(self) -> tuple[DocChange, ...]:
        return tuple(c for c in self.changes if c.touches_vault)

    def counts(self) -> dict[str, int]:
        """``{"added": n, "modified": n, "deleted": n}`` over vault documents."""
        counted = Counter(c.status.value for c in self.vault_changes)
        return {status.value: counted.get(status.value, 0) for status in ChangeStatus}

    def paths(self, status: ChangeStatus) -> tuple[str, ...]:
        return tuple(c.path for c in self.vault_changes if c.status is status)

    def lost_paths(self) -> tuple[str, ...]:
        """The deleted paths the guard counts — what a hold has to ask about.

        A move's source path is left out, because a hold lists what the round
        would *remove* and a document that turned up under another name was
        not removed. Listing it would put 56 relocations in front of the user
        beside the 25 deletions the guard actually stopped, with nothing to
        tell them apart.
        """
        return tuple(c.path for c in losses(self.vault_changes))
