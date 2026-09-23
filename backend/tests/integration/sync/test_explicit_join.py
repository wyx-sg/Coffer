"""Joining is explicit (spec vault-sync "Report a join before applying it").

A machine with no pointer is joining, and only ``adopt`` may join. The
timer's round and ``POST /sync/run`` on such a machine apply nothing, push
nothing and say the machine is waiting to join — once, not once per interval.
"""

from __future__ import annotations

import logging
import pathlib
from datetime import UTC, datetime

import pytest

from coffer.application.sync.worker import ConvergeWorker
from coffer.domain.sync.convergence import ConvergeRun, ConvergeStatus, GuardDirection, JoinKind
from coffer.domain.sync.diff import ChangeStatus
from tests.integration.sync.harness import settle, two_machines

pytestmark = pytest.mark.timeout(120)

_CONVERGENCE_LOGGER = "coffer.application.sync.convergence"


@pytest.fixture
async def pair(tmp_path: pathlib.Path):
    a, b = await two_machines(tmp_path)
    yield a, b
    await a.close()
    await b.close()


async def test_an_ordinary_round_on_a_machine_that_has_not_joined_applies_and_pushes_nothing(
    pair,
) -> None:
    a, b = pair
    a.write_knowledge("notes", "from-a", "written on the laptop\n")
    await a.adopt()
    b.write_knowledge("notes", "from-b", "written on the desktop\n")
    await b.remote_config()
    service = b.service()

    first = await service.run_once()
    second = await service.run_once()

    for run in (first, second):
        assert run.status is ConvergeStatus.AWAITING_JOIN
        # Detected, not applied: the round says what the join would be.
        assert run.join is JoinKind.NEW
        assert run.join_report is not None
        assert run.join_report.remote_changed == 1
        assert run.join_report.vault_documents == 1
        assert not run.applied and not run.published and run.commit is None
    assert await b.state.pointer() is None
    assert b.read_knowledge("notes", "from-a") is None
    assert "knowledge/notes/from-b.md" not in await b.remote_paths()
    # One situation, one history row and one audit event, however many ticks.
    assert len(await service.runs(10)) == 1
    assert await b.audit_events("sync_run") == 1

    joined = await service.run_once(adopt=True)

    assert joined.join is JoinKind.NEW
    assert joined.status is ConvergeStatus.OK, joined.error
    assert b.read_knowledge("notes", "from-a") == "written on the laptop\n"
    assert "knowledge/notes/from-b.md" in await b.remote_paths()


async def test_a_machine_that_joined_converges_on_an_ordinary_round(pair) -> None:
    a, b = pair
    await a.adopt()
    await b.adopt()
    a.write_knowledge("notes", "later", "after both joined\n")
    await a.converge()
    await b.remote_config()

    run = await b.service().run_once()

    assert run.status is ConvergeStatus.OK, run.error
    assert b.read_knowledge("notes", "later") == "after both joined\n"


def test_the_worker_logs_a_machine_waiting_to_join_quietly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = datetime.now(tz=UTC)
    waiting = ConvergeRun(status=ConvergeStatus.AWAITING_JOIN, started_at=now, finished_at=now)

    with caplog.at_level(logging.DEBUG, logger="coffer.application.sync.worker"):
        ConvergeWorker._log(waiting)

    assert [r.levelno for r in caplog.records] == [logging.DEBUG]


async def test_an_ordinary_round_on_a_machine_without_a_pointer_still_detects_the_join(
    pair,
) -> None:
    """Detection runs on every round without a pointer; applying waits for adopt.

    B has converged here before and lost its pointer to a reinstall. An
    ordinary round recognises it as returning and recovers its base from its
    own descriptor — and reports that, rather than acting on it.
    """
    a, b = pair
    a.write_knowledge("notes", "shared", "one\n")
    await settle(a, b)
    await settle(a, b)
    descriptor = await b.remote_text(f"machines/{b.machine_id}.yaml")
    assert descriptor is not None
    recorded_base = next(
        line.split(":", 1)[1].strip()
        for line in descriptor.splitlines()
        if line.startswith("last_converged_commit:")
    )
    b.state.forget()
    b.forget_worktree()
    a.write_knowledge("notes", "while-away", "written while b was gone\n")
    await a.converge()
    await b.remote_config()

    run = await b.service().run_once()

    assert run.status is ConvergeStatus.AWAITING_JOIN
    assert run.join is JoinKind.RETURNING
    assert run.join_report is not None
    assert run.join_report.base == recorded_base
    assert run.join_report.last_converged_on is not None
    assert run.join_report.remote_changed is not None and run.join_report.remote_changed >= 1
    # Reported, not applied.
    assert await b.state.pointer() is None
    assert b.read_knowledge("notes", "while-away") is None


async def test_a_new_machine_whose_join_stopped_on_a_conflict_converges_once_resolved(
    pair,
) -> None:
    a, b = pair
    a.write_knowledge("notes", "clash", "A's version\n")
    await a.adopt()
    b.write_knowledge("notes", "clash", "B's version\n")
    await b.remote_config()
    service = b.service()

    joined = await service.run_once(adopt=True)

    assert joined.status is ConvergeStatus.CONFLICT
    assert joined.join is JoinKind.NEW
    # The join happened: this machine has a base now, and every surface says so.
    assert await service.joined() is True
    # Resolved by the user, in their own vault.
    b.write_knowledge("notes", "clash", "A's version\n")

    run = await service.run_once()

    assert run.status in (ConvergeStatus.OK, ConvergeStatus.NO_CHANGE), run.error
    assert run.join is None
    assert "knowledge/notes/clash.md" in await b.remote_paths()


async def test_confirming_a_held_join_lets_it_finish(pair) -> None:
    """A returning machine whose vault is gone joins into a publish-side hold;
    the user's confirmation is spent on that round, not on a no-op."""
    a, b = pair
    for i in range(6):
        a.write_knowledge("notes", f"n{i}", f"note {i}\n")
    await settle(a, b)
    b.state.forget()
    b.forget_worktree()
    await b.wipe_vault()
    await b.remote_config()
    service = b.service()

    held = await service.run_once(adopt=True)
    assert held.status is ConvergeStatus.AWAITING_CONFIRMATION
    assert held.pending is not None and held.pending.direction is GuardDirection.PUBLISH

    confirmed = await service.confirm()

    assert confirmed.status is ConvergeStatus.OK, confirmed.error
    assert "knowledge/notes/n0.md" in confirmed.published.paths(ChangeStatus.DELETED)
    assert "knowledge/notes/n0.md" not in await b.remote_paths()


async def test_an_unreachable_pointer_waits_for_adopt_and_says_so_once(
    pair, caplog: pytest.LogCaptureFixture
) -> None:
    a, b = pair
    await settle(a, b)
    await b.state.set_pointer("0123456789abcdef0123456789abcdef01234567")
    await b.remote_config()
    service = b.service()

    with caplog.at_level(logging.INFO, logger=_CONVERGENCE_LOGGER):
        first = await service.run_once()
        second = await service.run_once()

    assert first.status is second.status is ConvergeStatus.AWAITING_JOIN
    said = [r for r in caplog.records if "unreachable" in r.getMessage()]
    assert len(said) == 1
    assert said[0].levelno == logging.INFO
