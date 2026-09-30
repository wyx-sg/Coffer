"""The two checks a merged tree passes before it is checked out
(spec vault-sync "Hold a round that would lose too much", spec vault-storage
"Admit every vault write through one compare-and-swap path").

- **Validation.** The merged tree meets the same validator a person's edit and
  a daemon write meet; a file that fails is a conflict the person answers,
  never something checked out.
- **The deletion breaker, both directions.** Incoming is what the round
  would remove from this vault (``L -> T``); outgoing is what this machine's
  own commits remove from the shared history (``base -> L``), so a local mass
  deletion — a wiped folder, a bad restore — is held before it is pushed.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.application.sync.round_ports import SyncGitPort
from coffer.application.sync.round_trees import TreeReader
from coffer.domain.sync.breaker import PathDelta, breached, losses, totals
from coffer.domain.sync.stops import ConflictFile, ConflictReason, Hold, HoldDirection
from coffer.domain.vault.findings import blocking
from coffer.domain.vault.layout import area_of
from coffer.domain.vault.writes import Change, Validator
from coffer.domain.vault.writes import TreeReader as HistoryReader


def _deltas(git: SyncGitPort, a: str | None, b: str) -> list[PathDelta]:
    return [
        PathDelta(c.path, c.status, c.old if c.status == "D" else c.new) for c in git.diff(a, b)
    ]


def hold_for(
    git: SyncGitPort,
    reader: TreeReader,
    *,
    before: str | None,
    after: str,
    direction: HoldDirection,
) -> Hold | None:
    """A hold when ``before -> after`` loses too much, else ``None``."""
    if before is None:
        return None
    deltas = _deltas(git, before, after)
    if not any(d.status == "D" for d in deltas):
        return None
    lost = losses(
        deltas,
        renames=git.renames(before, after),
        uids_before=reader.uids(before),
        uids_after=reader.uids(after).values(),
    )
    breaches = breached(lost, totals(git.files(before)))
    if not breaches:
        return None
    return Hold(direction=direction, breaches=tuple(breaches), paths=tuple(lost))


def invalid_files(
    git: SyncGitPort,
    validate: Validator | None,
    history: HistoryReader,
    *,
    local: str,
    merged: str,
) -> list[ConflictFile]:
    """The files of ``merged`` that validation refuses, as conflicts."""
    if validate is None:
        return []
    changed = git.diff(local, merged)
    if not changed:
        return []
    wanted = [c.new for c in changed if c.new] + [c.old for c in changed if c.old]
    data = git.blobs(wanted)
    changes: Sequence[Change] = [
        Change(
            c.path,
            data.get(c.new) if c.new else None,
            data.get(c.old) if c.old else None,
        )
        for c in changed
    ]
    refused = blocking(validate(changes, history).findings)
    by_path = {c.path: c for c in changed}
    out: list[ConflictFile] = []
    for path in sorted({f.path for f in refused}):
        c = by_path.get(path)
        out.append(
            ConflictFile(
                path=path,
                area=area_of(path),
                reason=ConflictReason.INVALID_MERGE,
                ours=c.old if c else None,
                theirs=c.new if c else None,
            )
        )
    return out


__all__ = ["hold_for", "invalid_files"]
