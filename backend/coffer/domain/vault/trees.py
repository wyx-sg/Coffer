"""What git answers about two trees: a merge's result and the paths that differ."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConflictEntry:
    """One conflicted path: the blob each side holds (``None`` where that
    side deleted the file or never had it)."""

    path: str
    base: str | None
    ours: str | None
    theirs: str | None


@dataclass(frozen=True)
class MergeResult:
    tree: str
    conflicts: tuple[ConflictEntry, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        return not self.conflicts


@dataclass(frozen=True)
class TreeChange:
    """One path that differs between two trees."""

    path: str
    status: str  # "A", "M", "D"
    old: str | None
    new: str | None


__all__ = ["ConflictEntry", "MergeResult", "TreeChange"]
