"""The curation gate reads the round that last settled the merge, not the last round.

A conflict is outstanding until a round merges again (spec vault-sync "Never
overlap a curation pass and a round"). A round that failed on the network, or that
did not run because sync was switched off, never reached the merge, so it says
nothing about whether the conflict was resolved.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.sync.service_history import HistoryMixin
from coffer.domain.sync.convergence import ConvergeRun, ConvergeStatus, RunRecord


class _Remotes:
    def __init__(self) -> None:
        self.rounds: list[ConvergeRun] = []

    async def last_run(self) -> ConvergeRun | None:
        return self.rounds[-1] if self.rounds else None

    async def list_runs(self, limit: int = 500) -> list[RunRecord]:
        newest_first = list(reversed(self.rounds))[:limit]
        return [RunRecord(id=i, run=r) for i, r in enumerate(newest_first)]


class _State:
    async def pending(self) -> None:
        return None


class _History(HistoryMixin):
    def __init__(self) -> None:
        self._remotes = _Remotes()  # type: ignore[assignment]
        self._state = _State()  # type: ignore[assignment]

    def ran(self, status: ConvergeStatus) -> None:
        now = datetime.now(tz=UTC)
        self._remotes.rounds.append(  # type: ignore[attr-defined]
            ConvergeRun(status=status, started_at=now, finished_at=now)
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "unsettling",
    [
        ConvergeStatus.FAILED,
        ConvergeStatus.DISABLED,
        ConvergeStatus.AWAITING_JOIN,
        # A hold answered by rejecting it: pending() is clear again, but
        # nothing converged.
        ConvergeStatus.AWAITING_CONFIRMATION,
    ],
)
async def test_a_round_that_never_merged_does_not_clear_a_conflict(
    unsettling: ConvergeStatus,
) -> None:
    history = _History()
    history.ran(ConvergeStatus.OK)
    assert await history.divergence_outstanding() is False

    history.ran(ConvergeStatus.CONFLICT)
    history.ran(unsettling)
    history.ran(ConvergeStatus.FAILED)
    assert await history.divergence_outstanding() is True

    history.ran(ConvergeStatus.NO_CHANGE)
    assert await history.divergence_outstanding() is False


@pytest.mark.anyio
async def test_a_round_whose_push_failed_still_merged_and_clears_it() -> None:
    history = _History()
    history.ran(ConvergeStatus.CONFLICT)
    history.ran(ConvergeStatus.PUSH_FAILED)
    assert await history.divergence_outstanding() is False


@pytest.mark.anyio
async def test_no_round_that_merged_means_nothing_outstanding() -> None:
    history = _History()
    assert await history.divergence_outstanding() is False
    history.ran(ConvergeStatus.FAILED)
    assert await history.divergence_outstanding() is False
