"""What an upgrade carried, per class, and what it could not."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MigrationReport:
    #: ``fresh`` (no old database), ``migrated``, ``already`` (runs.db exists).
    outcome: str
    counts: dict[str, int] = field(default_factory=dict)
    #: Rows or files that could not be carried, one line each.
    skipped: list[str] = field(default_factory=list)
    #: Things a person may want to act on: links into moved trees, the old
    #: sync working tree, a sync remote that must be rebuilt.
    notices: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"outcome: {self.outcome}"]
        out += [f"  {name}: {n}" for name, n in self.counts.items()]
        out += [f"not carried: {s}" for s in self.skipped]
        out += [f"note: {n}" for n in self.notices]
        return out


__all__ = ["MigrationReport"]
