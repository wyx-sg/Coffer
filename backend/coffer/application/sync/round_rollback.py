"""Rolling a round back from its safety snapshot
(spec vault-sync "Snapshot before applying and roll back from it").

Before a round checks anything out it tags the vault as it was
(``coffer/pre-apply/<time>``, the ten newest kept). Rolling back is a new
commit on this machine — never ``HEAD`` moved backwards — that puts every file
the round changed back to its snapshot version; the next round pushes it, so
the other machines follow. A file edited since the round is left as it is and
reported: rolling back never discards later work.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.application.sync.round_engine import Recorder, RoundEngine
from coffer.domain.error_base import CofferError
from coffer.domain.sync.rounds import AppliedChange, RoundRecord, RoundStatus
from coffer.domain.vault.writers import OP_RESTORE, WRITER_USER, CommitMeta
from coffer.domain.vault.writes import Expect


class SyncNothingToRollBack(CofferError):  # noqa: N818
    """The round applied nothing, or its snapshot is gone. Maps to 409."""

    code = "SYNC_NOTHING_TO_ROLL_BACK"


@dataclass(frozen=True)
class RollbackPlan:
    snapshot: str
    snapshot_commit: str
    #: What rolling back reverses: each path and what it goes back to.
    reverses: tuple[AppliedChange, ...]
    #: Files edited since the round; left as they are.
    kept: tuple[str, ...]


def plan(engine: RoundEngine, record: RoundRecord) -> RollbackPlan:
    d = engine.d
    if not record.snapshot or not record.to_commit or not record.applied:
        raise SyncNothingToRollBack("this round applied nothing to roll back")
    tags = {name: commit for name, commit, _ in d.git.snapshots()}
    commit = tags.get(record.snapshot)
    if commit is None:
        raise SyncNothingToRollBack(f"the snapshot {record.snapshot} is no longer kept")
    reverses: list[AppliedChange] = []
    kept: list[str] = []
    head = d.git.head() or ""
    for change in record.applied:
        now = d.git.files(head, change.path).get(change.path)
        then = d.git.files(record.to_commit, change.path).get(change.path)
        if now != then:
            kept.append(change.path)
            continue
        before = d.git.files(commit, change.path).get(change.path)
        status = "removed" if before is None else "added" if then is None else "modified"
        reverses.append(AppliedChange(change.path, status))
    return RollbackPlan(record.snapshot, commit, tuple(reverses), tuple(kept))


def rollback(engine: RoundEngine, record: RoundRecord, *, actor: str) -> RoundRecord:
    d = engine.d
    rec = Recorder(d, d.now(), "manual")
    shown = plan(engine, record)
    meta = CommitMeta(
        writer=WRITER_USER,
        operation=OP_RESTORE,
        summary=f"Rolled back the round of {record.started_at}",
        actor=actor,
        restored_from=shown.snapshot_commit,
    )
    head = d.git.head()
    with d.writer.begin(meta) as txn:
        for change in shown.reverses:
            data = d.git.read(shown.snapshot_commit, change.path)
            if data is None:
                txn.delete(change.path, Expect.HEAD)
            else:
                txn.write(change.path, data, Expect.HEAD)
    return rec(
        RoundStatus.ROLLED_BACK,
        from_commit=head,
        to_commit=txn.version or head,
        snapshot=shown.snapshot,
        applied=shown.reverses,
        detail=f"kept {len(shown.kept)} files edited since" if shown.kept else None,
    )


__all__ = ["RollbackPlan", "SyncNothingToRollBack", "plan", "rollback"]
