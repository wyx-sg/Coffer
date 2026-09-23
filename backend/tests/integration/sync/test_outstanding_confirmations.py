"""What an unanswered confirmation does on every tick after the first.

These drive the real :class:`ConvergeService` over a real SQLite database
rather than the round alone, because the behaviour under test is the
*recording*: the round reporting a hold, the remote's row, the history the Sync
page reads and the audit trail, all agreeing that one situation is one entry.

The measured defect. A vault held at the publish-side guard collected ten
``awaiting_confirmation`` rows between 16:12 on one day and 16:15 the next, one
per hourly tick, every one of them reading ``+0 ~0 -0`` in both directions
because the round returned before it computed a diff at all. Ten rows carried
no more information than one, and the ``+0 ~0 -0`` actively misled: it read as
though the round had found nothing to do, when what it had found was a question
nobody had answered (spec vault-sync "Release a hold whose diff no longer
breaches", "Record one outstanding confirmation once").
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.audit import AuditEventType
from coffer.domain.sync.convergence import ConvergeStatus, GuardDirection
from tests.integration.sync.harness import settle, two_machines

pytestmark = pytest.mark.timeout(180)

#: How many times the timer looks at the same unanswered question.
TICKS = 5


@pytest.fixture
async def pair(tmp_path: pathlib.Path):
    a, b = await two_machines(tmp_path)
    yield a, b
    await a.close()
    await b.close()


async def _vault_held_at_the_publish_guard(a, b):
    """A vault that has deleted a third of its notes and been held for it."""
    names = [f"n{i:02d}" for i in range(30)]
    for name in names:
        a.write_knowledge("notes", name, f"body of {name}\n")
    await settle(a, b)
    for name in names[:10]:
        a.delete_knowledge("notes", name)
    await a.remote_config()


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an unanswered confirmation is reported once, not once a tick"
)
async def test_five_ticks_on_one_outstanding_confirmation_record_one_round(pair) -> None:
    a, b = pair
    await _vault_held_at_the_publish_guard(a, b)
    service = a.service()

    runs = [await service.run_once() for _ in range(TICKS)]

    assert [r.status for r in runs] == [ConvergeStatus.AWAITING_CONFIRMATION] * TICKS
    # The first tick raises the question; the four after it re-derive the same
    # diff and find the same question, which is not news.
    assert [r.hold_already_reported for r in runs] == [False, True, True, True, True]

    records = await service.runs()
    assert len(records) == 1, f"{len(records)} rows for one outstanding confirmation"
    assert await a.audit_events(AuditEventType.SYNC_RUN.value) == 1

    # The row is the one that first reported it, re-stamped: the moment the
    # vault stopped is still readable, and so is the fact that it is still
    # ticking rather than dead.
    row = records[0].run
    assert row.pending is not None
    assert row.pending.raised_at == runs[0].pending.raised_at
    assert row.started_at == runs[0].started_at
    assert row.finished_at >= runs[-1].started_at

    # And the Sync page still sees an outstanding confirmation to act on: it
    # reads the remote's last round, not the history.
    last = await service.last_run()
    assert last is not None and last.pending is not None
    assert last.pending.direction is GuardDirection.PUBLISH
    assert len(last.pending.paths) == 10


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an unanswered confirmation is reported once, not once a tick"
)
async def test_answering_the_confirmation_produces_a_further_round(pair) -> None:
    """Coalescing is for the question, not for the answer. A confirmation is a
    thing the user did and it gets its own row, so the history reads as
    "held since 16:12, published at 09:40" rather than as a single row that
    silently changed its mind."""
    a, b = pair
    await _vault_held_at_the_publish_guard(a, b)
    service = a.service()
    for _ in range(TICKS):
        await service.run_once()

    confirmed = await service.confirm()

    assert confirmed.status is ConvergeStatus.OK, confirmed.error
    records = await service.runs()
    assert len(records) == 2
    assert [r.run.status for r in records] == [
        ConvergeStatus.OK,
        ConvergeStatus.AWAITING_CONFIRMATION,
    ]
    assert not [p for p in await a.remote_paths() if p.startswith("knowledge/notes/n0")]


async def test_a_hold_that_has_become_a_different_question_is_asked_afresh(pair) -> None:
    """The coalescing is keyed on the question being the same one. A vault that
    has since lost more documents is a different question — a different list in
    front of the user — so it gets its own row and its own timestamp. Without
    this, "one row per situation" would quietly become "one row, forever,
    whatever happens next"."""
    a, b = pair
    await _vault_held_at_the_publish_guard(a, b)
    service = a.service()
    first = await service.run_once()
    await service.run_once()
    assert len(await service.runs()) == 1

    # Five more notes go. The user is now being asked about fifteen documents,
    # not the ten they were shown.
    for i in range(10, 15):
        a.delete_knowledge("notes", f"n{i:02d}")

    again = await service.run_once()

    assert again.status is ConvergeStatus.AWAITING_CONFIRMATION
    assert again.hold_already_reported is False
    assert again.pending is not None
    assert again.pending.breaches == (("knowledge", 15, 30),)
    assert first.pending is not None
    assert again.pending.raised_at > first.pending.raised_at
    assert len(await service.runs()) == 2
