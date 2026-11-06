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

from coffer.application.sync.round_ports import RoundStatePort, SyncGitPort
from coffer.application.sync.round_trees import TreeReader
from coffer.domain.sync.breaker import PathDelta, breached, losses, totals, unaccounted
from coffer.domain.sync.stops import ConflictFile, ConflictReason, Hold, HoldDirection
from coffer.domain.vault.findings import blocking
from coffer.domain.vault.history import REMOVED
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
    history: tuple[str | None, str] | None = None,
    approved: frozenset[str] = frozenset(),
) -> Hold | None:
    """A hold when ``before -> after`` loses too much, else ``None``.

    ``history`` is the commit range ``(since, until)`` the deletions were made
    in. A loss whose newest deleting commit there is accounted for
    (``accounted_for``) is set aside; so is one a person already ``approved``
    when they confirmed an earlier hold of this round."""
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
    before_totals = totals(git.files(before))
    if not breached(lost, before_totals):
        return None
    if history is not None:
        lost = unaccounted(lost, deleted_by(git, *history), before_totals)
    lost = [p for p in lost if p not in approved]
    breaches = breached(lost, before_totals)
    if not breaches:
        return None
    return Hold(direction=direction, breaches=tuple(breaches), paths=tuple(lost))


def deleted_by(git: SyncGitPort, since: str | None, until: str) -> dict[str, tuple[str, str]]:
    """``(writer, operation)`` of the newest commit in ``since..until`` that
    deleted each path. Merge commits list no paths, so a deletion that only a
    merge made stays unattributed and counted."""
    out: dict[str, tuple[str, str]] = {}
    for commit in git.commits_between(since, until):  # newest first
        for change in commit.paths:
            if change.status == REMOVED and change.path not in out:
                out[change.path] = (commit.meta.writer, commit.meta.operation)
    return out


def approved_losses(state: RoundStatePort, tip: str) -> frozenset[str]:
    """The files a person confirmed deleting, while the remote is where it was
    when they did (ADR sync-deletion-breaker): this machine's own later edits
    — a plaintext fix, a new note — do not void the answer, a moved remote does."""
    confirmed = state.confirmed()
    if confirmed is None or confirmed[1] != tip:
        return frozenset()
    return state.approved_losses()


def merge_hold(
    git: SyncGitPort,
    reader: TreeReader,
    state: RoundStatePort,
    *,
    local: str,
    tip: str,
    base: str | None,
    tree: str,
) -> Hold | None:
    """A merged round's hold: what it would remove here (``local -> tree``,
    deleted in ``base..tip``), else what this machine's commits remove
    (``base -> local``)."""
    approved = approved_losses(state, tip)
    hold = hold_for(
        git,
        reader,
        before=local,
        after=tree,
        direction=HoldDirection.INCOMING,
        history=(base, tip),
        approved=approved,
    )
    if hold is None and base is not None:
        hold = hold_for(
            git,
            reader,
            before=base,
            after=local,
            direction=HoldDirection.OUTGOING,
            history=(base, local),
            approved=approved,
        )
    return hold


def push_hold(
    git: SyncGitPort, reader: TreeReader, state: RoundStatePort, *, local: str, tip: str
) -> Hold | None:
    """A push-only round's hold: what this machine's commits remove from ``tip``."""
    return hold_for(
        git,
        reader,
        before=tip,
        after=local,
        direction=HoldDirection.OUTGOING,
        history=(tip, local),
        approved=approved_losses(state, tip),
    )


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


__all__ = [
    "approved_losses",
    "deleted_by",
    "hold_for",
    "invalid_files",
    "merge_hold",
    "push_hold",
]
