"""SyncAttentionSource: the last round, while a remote is configured."""

from __future__ import annotations

from datetime import timedelta

import pytest

from coffer.application.attention import AttentionAction, Severity
from coffer.application.sync.attention import SyncAttentionSource
from coffer.domain.sync.backup import BackupRemote
from coffer.domain.sync.convergence import (
    ConvergeRun,
    ConvergeStatus,
    GuardDirection,
    PendingConfirmation,
)
from tests.unit.application._attention_fakes import T0

REMOTE = BackupRemote(url="https://git.example.test/me/vault.git")
RAISED = T0 + timedelta(minutes=5)


class FakeSync:
    def __init__(self, remote: BackupRemote | None, run: ConvergeRun | None) -> None:
        self.remote = remote
        self.run = run

    async def get_remote(self) -> BackupRemote | None:
        return self.remote

    async def last_run(self) -> ConvergeRun | None:
        return self.run


def _run(status: ConvergeStatus, **kw) -> ConvergeRun:  # type: ignore[no-untyped-def]
    return ConvergeRun(status=status, started_at=T0, finished_at=T0 + timedelta(seconds=3), **kw)


async def test_conflict_is_an_error_asking_for_another_round() -> None:
    run = _run(ConvergeStatus.CONFLICT, conflicts=("notes/a.md", "notes/b.md"))
    [item] = await SyncAttentionSource(sync=FakeSync(REMOTE, run)).items()
    assert (item.kind, item.uid, item.title) == ("sync", None, "Sync")
    assert item.reason_code == "sync_conflict"
    assert item.severity is Severity.ERROR
    assert "2 files" in item.reason
    assert item.since == T0
    assert item.action == AttentionAction(verb="run", method="POST", path="/api/v1/sync/run")


async def test_held_deletions_are_a_warning_that_opens_the_status_not_the_confirm() -> None:
    pending = PendingConfirmation(
        direction=GuardDirection.APPLY,
        commit="abc",
        remote_tip="def",
        breaches=(("notes", 9, 10),),
        paths=("notes/a.md",),
        raised_at=RAISED,
    )
    run = _run(ConvergeStatus.AWAITING_CONFIRMATION, pending=pending)
    [item] = await SyncAttentionSource(sync=FakeSync(REMOTE, run)).items()
    assert item.reason_code == "sync_deletions_held"
    assert item.severity is Severity.WARNING
    assert item.since == RAISED
    assert item.action == AttentionAction(verb="review", method="GET", path="/api/v1/sync/status")


@pytest.mark.parametrize(
    "status",
    [
        ConvergeStatus.OK,
        ConvergeStatus.NO_CHANGE,
        ConvergeStatus.PUSH_FAILED,
        ConvergeStatus.DISABLED,
    ],
)
async def test_other_outcomes_report_nothing(status: ConvergeStatus) -> None:
    assert await SyncAttentionSource(sync=FakeSync(REMOTE, _run(status))).items() == []


async def test_no_remote_or_no_round_reports_nothing() -> None:
    conflict = _run(ConvergeStatus.CONFLICT)
    assert await SyncAttentionSource(sync=FakeSync(None, conflict)).items() == []
    assert await SyncAttentionSource(sync=FakeSync(REMOTE, None)).items() == []


async def test_a_raising_dependency_propagates() -> None:
    class Broken(FakeSync):
        async def last_run(self) -> ConvergeRun | None:
            raise RuntimeError("state unreadable")

    with pytest.raises(RuntimeError, match="state unreadable"):
        await SyncAttentionSource(sync=Broken(REMOTE, None)).items()


def test_source_belongs_to_the_vault_sync_feature() -> None:
    from coffer.domain.features import EXPERIMENTAL_FEATURES

    source = SyncAttentionSource(sync=FakeSync(None, None))
    assert source.name == "sync"
    assert source.feature in {f.key for f in EXPERIMENTAL_FEATURES}
    assert source.feature == "vault_sync"
