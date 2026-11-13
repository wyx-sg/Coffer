"""The check a merged tree passes before it is checked out
(spec vault-storage "Admit every vault write through one compare-and-swap path").

The merged tree meets the same validator a person's edit and a daemon write
meet; a file that fails is a conflict the person answers, never something
checked out.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.application.sync.round_ports import SyncGitPort
from coffer.domain.sync.stops import ConflictFile, ConflictReason
from coffer.domain.vault.findings import blocking
from coffer.domain.vault.layout import area_of
from coffer.domain.vault.writes import Change, Validator
from coffer.domain.vault.writes import TreeReader as HistoryReader


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


__all__ = ["invalid_files"]
