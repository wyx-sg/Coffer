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
#: read straight from the working tree; ``manifest.json`` carries the bundle's
#: restamped creation time and says nothing about vault state.
NON_VAULT_AREAS = frozenset({"machines", "manifest"})

DEFAULT_DELETION_SHARE = 0.2
DEFAULT_DELETION_FLOOR = 20


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

    @property
    def area(self) -> str:
        return area_of(self.path)

    @property
    def touches_vault(self) -> bool:
        return self.area not in NON_VAULT_AREAS


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
        """Areas whose deletions exceed the guard, as (area, deleted, total).

        ``totals`` is how many documents each area held **before** the change,
        so a share is measured against what is at risk rather than what
        survives. An area missing from ``totals`` is treated as empty, which
        makes any deletion in it a share of 1.0 — correct, because deleting
        from an area this side does not know about is not something to do
        unattended.
        """
        deleted = Counter(
            c.area for c in changes if c.status is ChangeStatus.DELETED and c.touches_vault
        )
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
