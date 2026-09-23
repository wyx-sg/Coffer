"""The single-row backup-remote config survives a round-trip (spec vault-sync).

Against a real SQLite file rather than a fake repo: the thing under test is
precisely that the schema holds one row and that every field comes back as it
went in, and an in-memory double would only assert our own assumptions about
SQLAlchemy.
"""

from __future__ import annotations

import dataclasses
import pathlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.sync.backup import BackupRemote
from coffer.domain.sync.convergence import (
    ConvergeRun,
    ConvergeStatus,
    GuardDirection,
    JoinKind,
    PendingConfirmation,
)
from coffer.domain.sync.diff import ChangeStatus, DiffSummary, DocChange
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.sync_remote_repo import SqlAlchemySyncRemoteRepo


@pytest.fixture
async def sm(tmp_path: pathlib.Path) -> AsyncIterator[async_sessionmaker]:  # type: ignore[type-arg]
    """A fresh empty vault database per test."""
    db = tmp_path / "coffer.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield session_maker(engine)
    finally:
        await engine.dispose()


async def test_absent_until_set(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    assert await repo.get() is None
    assert await repo.last_run() is None


async def test_set_then_get_round_trips_every_field(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    remote = BackupRemote(
        url="https://example.invalid/vault.git",
        branch="backup",
        credential_ref="sync.BACKUP_TOKEN",
        include_credentials=True,
        interval_seconds=900,
        enabled=True,
        worktree_path="~/.coffer/sync",
    )
    await repo.set(remote)
    assert await repo.get() == remote


@pytest.mark.acceptance(spec="vault-sync", scenario="sync stays off until a remote is configured")
async def test_set_twice_keeps_one_row(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/one.git"))
    await repo.set(BackupRemote(url="https://example.invalid/two.git"))
    got = await repo.get()
    assert got is not None
    assert got.url == "https://example.invalid/two.git"


async def test_clear_removes_it(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    await repo.clear()
    assert await repo.get() is None


async def test_record_run_round_trips_a_whole_round(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    """A round is columns plus one JSON document, and both halves come back.

    Only what a status surface reads at a glance is a column; everything else
    is written once as a single payload, so no column can disagree with the
    document beside it. This asserts the seam by putting a round with something
    in every field through it.
    """
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    started = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
    finished = datetime(2026, 9, 12, 9, 0, 30, tzinfo=UTC)
    run = ConvergeRun(
        status=ConvergeStatus.PUSH_FAILED,
        started_at=started,
        finished_at=finished,
        join=JoinKind.RETURNING,
        applied=DiffSummary.of([DocChange("knowledge/notes/a.md", ChangeStatus.ADDED)]),
        published=DiffSummary.of([DocChange("skills/gone/SKILL.md", ChangeStatus.DELETED)]),
        commit="abc1234",
        conflicts=("knowledge/notes/contested.md",),
        agent_resolved=("resources/mcp_server/x.yaml",),
        failures=(("resources/agent/codex.yaml", "config dir missing here"),),
        locked_refs=("mcp/files/token",),
        error="offline",
    )

    await repo.record_run(run)

    got = await repo.last_run()
    assert got is not None
    assert got.status is ConvergeStatus.PUSH_FAILED
    assert got.join is JoinKind.RETURNING
    assert got.commit == "abc1234"
    assert got.error == "offline"
    assert got.started_at == started
    assert got.finished_at == finished
    assert got.applied.paths(ChangeStatus.ADDED) == ("knowledge/notes/a.md",)
    assert got.published.paths(ChangeStatus.DELETED) == ("skills/gone/SKILL.md",)
    assert got.conflicts == ("knowledge/notes/contested.md",)
    assert got.agent_resolved == ("resources/mcp_server/x.yaml",)
    assert got.failures == (("resources/agent/codex.yaml", "config dir missing here"),)
    assert got.locked_refs == ("mcp/files/token",)
    assert got.pending is None


async def test_a_held_round_comes_back_with_what_it_would_delete(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    """The user answers a held round from what the surface shows them, so the
    breach list and the paths have to survive the write."""
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    raised = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    pending = PendingConfirmation(
        direction=GuardDirection.PUBLISH,
        commit="def5678",
        remote_tip="0123456",
        breaches=(("knowledge", 9, 10),),
        paths=tuple(f"knowledge/notes/n{i}.md" for i in range(9)),
        raised_at=raised,
    )

    await repo.record_run(
        ConvergeRun(
            status=ConvergeStatus.AWAITING_CONFIRMATION,
            started_at=raised,
            finished_at=raised,
            pending=pending,
        )
    )

    got = await repo.last_run()
    assert got is not None and got.pending is not None
    assert got.pending.direction is GuardDirection.PUBLISH
    assert got.pending.commit == "def5678"
    assert got.pending.remote_tip == "0123456"
    assert got.pending.breaches == (("knowledge", 9, 10),)
    assert got.pending.paths == pending.paths
    assert got.pending.raised_at == raised


async def test_a_push_failed_round_keeps_the_commit_still_waiting(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    """A round that reports no new commit must not erase the one outstanding:
    that revision is what the user is being told is still unpushed."""
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    at = datetime(2026, 9, 12, tzinfo=UTC)
    await repo.record_run(
        ConvergeRun(status=ConvergeStatus.OK, started_at=at, finished_at=at, commit="abc1234")
    )

    await repo.record_run(
        ConvergeRun(status=ConvergeStatus.FAILED, started_at=at, finished_at=at, error="boom")
    )

    got = await repo.last_run()
    assert got is not None
    assert got.status is ConvergeStatus.FAILED
    assert got.commit == "abc1234"


async def test_a_run_recorded_with_no_remote_configured_is_discarded(
    sm: async_sessionmaker,
) -> None:  # type: ignore[type-arg]
    """A run result belongs to a remote. Clearing the remote mid-round must
    discard the result rather than resurrect the row it described."""
    repo = SqlAlchemySyncRemoteRepo(sm)
    at = datetime(2026, 9, 12, tzinfo=UTC)

    await repo.record_run(
        ConvergeRun(status=ConvergeStatus.OK, started_at=at, finished_at=at, commit="abc1234")
    )

    assert await repo.get() is None
    assert await repo.last_run() is None


# --- the run history --------------------------------------------------------


async def test_the_history_is_empty_until_a_round_runs(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    assert await repo.list_runs() == []


async def test_recording_a_round_appends_it_to_the_history(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    """Every round survives, with the whole report — not just the newest.

    The remote row keeps exactly one round. This asserts the other half of
    ``record_run``: the same round, with its payload intact, also lands in the
    history it can be compared against later.
    """
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    started = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
    finished = datetime(2026, 9, 12, 9, 0, 30, tzinfo=UTC)
    run = ConvergeRun(
        status=ConvergeStatus.OK,
        started_at=started,
        finished_at=finished,
        join=JoinKind.NEW,
        applied=DiffSummary.of([DocChange("knowledge/notes/a.md", ChangeStatus.ADDED)]),
        published=DiffSummary.of([DocChange("skills/gone/SKILL.md", ChangeStatus.DELETED)]),
        commit="abc1234",
        agent_resolved=("resources/mcp_server/x.yaml",),
        locked_refs=("mcp/files/token",),
    )

    await repo.record_run(run)

    (record,) = await repo.list_runs()
    assert record.id > 0
    assert record.run == run


async def test_the_history_returns_the_rounds_newest_first(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    """Ordered by when they finished, and by id when that ties.

    SQLite stores the timestamp to no finer resolution than the value handed
    to it, so three rounds stamped identically — which is what a test, and a
    fast catch-up loop, actually produce — must still come back in the order
    they were written.
    """
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    at = datetime(2026, 9, 12, tzinfo=UTC)
    for commit in ("first", "second", "third"):
        await repo.record_run(
            ConvergeRun(status=ConvergeStatus.OK, started_at=at, finished_at=at, commit=commit)
        )

    records = await repo.list_runs()

    assert [r.run.commit for r in records] == ["third", "second", "first"]


async def test_the_history_keeps_a_commitless_round_commitless(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    """The remote row carries the previous commit forward, so the user can see
    which revision is still waiting to be pushed. A history row must not: it
    would claim a round produced a commit it never reached."""
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    at = datetime(2026, 9, 12, tzinfo=UTC)
    await repo.record_run(
        ConvergeRun(status=ConvergeStatus.OK, started_at=at, finished_at=at, commit="abc1234")
    )

    await repo.record_run(
        ConvergeRun(status=ConvergeStatus.FAILED, started_at=at, finished_at=at, error="boom")
    )

    newest, older = await repo.list_runs()
    assert newest.run.commit is None
    assert older.run.commit == "abc1234"
    last = await repo.last_run()
    assert last is not None and last.commit == "abc1234"


async def test_the_history_returns_at_most_the_limit_asked_for(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    at = datetime(2026, 9, 12, tzinfo=UTC)
    for i in range(5):
        await repo.record_run(
            ConvergeRun(status=ConvergeStatus.OK, started_at=at, finished_at=at, commit=f"c{i}")
        )

    assert [r.run.commit for r in await repo.list_runs(2)] == ["c4", "c3"]


async def test_a_round_recorded_with_no_remote_reaches_neither_store(
    sm: async_sessionmaker,
) -> None:  # type: ignore[type-arg]
    """The two writes are one step, so they are skipped together: a round
    discarded from the remote row must not survive in the history."""
    repo = SqlAlchemySyncRemoteRepo(sm)
    at = datetime(2026, 9, 12, tzinfo=UTC)

    await repo.record_run(
        ConvergeRun(status=ConvergeStatus.OK, started_at=at, finished_at=at, commit="abc1234")
    )

    assert await repo.last_run() is None
    assert await repo.list_runs() == []


# --- one outstanding confirmation, one row ("Record one outstanding confirmation
# once") ---


def _held(at: datetime, *, paths: int = 9) -> ConvergeRun:
    return ConvergeRun(
        status=ConvergeStatus.AWAITING_CONFIRMATION,
        started_at=at,
        finished_at=at,
        pending=PendingConfirmation(
            direction=GuardDirection.PUBLISH,
            commit="def5678",
            remote_tip="0123456",
            breaches=(("knowledge", paths, 10),),
            paths=tuple(f"knowledge/notes/n{i}.md" for i in range(paths)),
            raised_at=at,
        ),
    )


async def test_refreshing_a_round_re_stamps_its_row_instead_of_adding_one(
    sm: async_sessionmaker,
) -> None:  # type: ignore[type-arg]
    """The timer re-derives an unanswered confirmation every interval. The row
    that first reported it keeps its ``started_at`` — the moment the vault
    stopped — while its ``finished_at`` moves, which is how the same row says
    both "held since then" and "still ticking"."""
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    raised = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    await repo.record_run(_held(raised))

    later = datetime(2026, 9, 12, 11, 0, tzinfo=UTC)
    refreshed = dataclasses.replace(_held(raised), started_at=later, finished_at=later)
    assert await repo.refresh_run(refreshed) is True

    records = await repo.list_runs()
    assert len(records) == 1
    assert records[0].run.started_at == raised
    assert records[0].run.finished_at == later
    assert records[0].run.pending is not None
    assert records[0].run.pending.raised_at == raised
    last = await repo.last_run()
    assert last is not None and last.finished_at == later


async def test_a_refresh_with_no_round_to_refresh_reports_so(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))

    assert await repo.refresh_run(_held(datetime(2026, 9, 12, tzinfo=UTC))) is False
    assert await repo.list_runs() == []


async def test_a_refresh_never_writes_over_a_round_of_another_outcome(
    sm: async_sessionmaker,
) -> None:  # type: ignore[type-arg]
    """The invariant at the write seam: if anything else recorded a round
    between two ticks, the newest row is not the held one and must not be
    overwritten. The caller records normally instead."""
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    at = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    await repo.record_run(_held(at))
    await repo.record_run(
        ConvergeRun(
            status=ConvergeStatus.OK,
            started_at=datetime(2026, 9, 12, 10, 30, tzinfo=UTC),
            finished_at=datetime(2026, 9, 12, 10, 30, tzinfo=UTC),
            commit="abc1234",
        )
    )

    assert await repo.refresh_run(_held(at)) is False

    records = await repo.list_runs()
    assert [r.run.status for r in records] == [
        ConvergeStatus.OK,
        ConvergeStatus.AWAITING_CONFIRMATION,
    ]
