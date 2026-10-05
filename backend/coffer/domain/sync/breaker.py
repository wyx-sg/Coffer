"""When a round would lose too much (ADR sync-deletion-breaker, ADR
identity-is-the-uid-inside-the-file).

A round is **held** when, in any area and in either direction, its *losses*
reach 20 files, or reach 5 files that are more than half of what the area held
before. The share only counts from 5 files up, so tidying a small area — two
of three demo servers, a stale skill — goes through, while wiping most of one
is still asked about. It counts losses, not deletions:

- a **resource file** is lost only when its **uid** is gone from the other
  side — a path that disappears while its uid reappears under another name is
  a move by construction, with no similarity judgement;
- any **other file** is a move when its exact bytes land elsewhere in the same
  area, or git's own rename detection paired it with a file in the same area.

The empty blob never pairs anything, and a pairing that crosses areas is not a
move: same content, wrong place, is still asked about. ``machines/`` and the
manifest are never counted — they are the registry, not vault content.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from coffer.domain.vault.content_ids import EMPTY_BLOB
from coffer.domain.vault.layout import RESOURCES, area_of

SHARE = 0.5
FLOOR = 20
#: The fewest losses the share is judged on.
SHARE_MIN = 5
_NOT_COUNTED = frozenset({"machines", "manifest", "other"})


@dataclass(frozen=True)
class PathDelta:
    """One path's fate between two trees."""

    path: str
    #: ``A`` added, ``M`` modified, ``D`` deleted.
    status: str
    #: The blob it had before (deleted / modified) or after (added).
    blob: str | None


@dataclass(frozen=True)
class Breach:
    area: str
    lost: int
    total: int


def losses(
    deltas: Iterable[PathDelta],
    *,
    renames: Sequence[tuple[str, str]] = (),
    uids_before: Mapping[str, str] | None = None,
    uids_after: Iterable[str] = (),
) -> list[str]:
    """The deleted paths that lose content, moves excluded.

    ``uids_before`` maps each resource path on the losing side to its uid;
    ``uids_after`` is every uid the other side still holds.
    """
    deltas = list(deltas)
    still = set(uids_after)
    before = uids_before or {}
    received = {src for src, dst in renames if area_of(src) == area_of(dst)}
    landed: dict[str, set[str]] = {}
    for d in deltas:
        if d.status != "D" and d.blob:
            landed.setdefault(area_of(d.path), set()).add(d.blob)
    lost: list[str] = []
    for d in deltas:
        if d.status != "D" or area_of(d.path) in _NOT_COUNTED:
            continue
        if d.path.startswith(RESOURCES + "/"):
            uid = before.get(d.path)
            if uid is not None and uid in still:
                continue
            lost.append(d.path)
            continue
        if d.path in received:
            continue
        if d.blob and d.blob != EMPTY_BLOB and d.blob in landed.get(area_of(d.path), set()):
            continue
        lost.append(d.path)
    return sorted(lost)


def totals(paths: Iterable[str]) -> dict[str, int]:
    """How many files each area holds."""
    return dict(Counter(area_of(p) for p in paths))


def breached(
    lost: Iterable[str],
    before_totals: Mapping[str, int],
    *,
    share: float = SHARE,
    floor: int = FLOOR,
    share_min: int = SHARE_MIN,
) -> list[Breach]:
    """Areas whose losses reach the floor, or reach ``share_min`` and exceed
    the share. An area the losing side did not know about counts as empty."""
    counted = Counter(area_of(p) for p in lost)
    out: list[Breach] = []
    for area, count in sorted(counted.items()):
        total = before_totals.get(area, 0)
        if count >= floor or (count >= share_min and count > share * total):
            out.append(Breach(area, count, total))
    return out


__all__ = ["FLOOR", "SHARE", "SHARE_MIN", "Breach", "PathDelta", "breached", "losses", "totals"]
