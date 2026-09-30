"""What joining a remote will do, shown before anything happens
(spec vault-sync "Report a join before applying it").

A machine joins a remote it has never converged with in one of three ways:

- **empty** — the remote holds nothing: this machine becomes the first, and
  the first round pushes the whole vault;
- **new** — this machine has no history with the remote: the union is taken.
  Files only the remote has are pulled, files only this machine has are
  pushed, identical files need nothing, and a file both hold with different
  content is left exactly as it is here, not pushed, until the person
  chooses. Joining never removes a file on either side;
- **returning** — the remote carries this machine's descriptor with the last
  commit it converged at: that commit is the merge base, and the join is an
  ordinary three-way merge (so this machine's own deletions since then are
  real deletions, guarded by the breaker).
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum


class JoinKind(StrEnum):
    EMPTY = "empty"
    NEW = "new"
    RETURNING = "returning"


@dataclasses.dataclass(frozen=True)
class AreaCount:
    area: str
    files: int


@dataclasses.dataclass(frozen=True)
class JoinPreview:
    kind: JoinKind
    remote_tip: str | None
    #: The machine that pushed the remote's newest commit, and when.
    pushed_by: str | None = None
    pushed_at: str | None = None
    pulled: tuple[AreaCount, ...] = ()
    same: int = 0
    differ: tuple[str, ...] = ()
    pushed: tuple[AreaCount, ...] = ()
    #: Returning only: what the three-way merge would delete or stop on.
    deleted: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    #: Resources of one kind and name with different uids: the join stops
    #: on them and asks which to keep, or to rename one.
    same_name: tuple[str, ...] = ()
    base: str | None = None

    @property
    def pulled_files(self) -> int:
        return sum(a.files for a in self.pulled)

    @property
    def pushed_files(self) -> int:
        return sum(a.files for a in self.pushed)


__all__ = ["AreaCount", "JoinKind", "JoinPreview"]
