"""Buffered-writer coverage for MCPInvocationRepo.

The production composition root runs the repo in *buffered* mode: insert()
enqueues and a background writer task drains the queue on a batch-size or
interval trigger, started/stopped over the daemon lifecycle. test_repos.py
only exercises the synchronous fallback (no start()), so the batching and —
most importantly — the shutdown drain were untested. The shutdown-drain case
is the data-loss class the buffering introduced: stop() MUST flush every row
still queued, or tool-call audit rows vanish on daemon restart.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from coffer.domain.mcp.capability import MCPInvocation
from coffer.infrastructure.mcp.invocation_writer import MCPInvocationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

#: An opaque uuid4 hex, the shape a real resource uid has.
_FS_UID = "aa11bb22cc33dd44ee55ff6677889900"


async def _make_repo(tmp_path, **kwargs):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    return MCPInvocationRepo(sm, **kwargs), engine


def _inv(key: str) -> MCPInvocation:
    return MCPInvocation(
        id=None,
        timestamp=datetime.now(tz=UTC),
        resource_uid=_FS_UID,
        capability_type="tool",
        capability_key=key,
        duration_ms=1,
        status="ok",
    )


@pytest.mark.asyncio
async def test_buffered_insert_flushes_by_batch_size(tmp_path):
    """Once flush_batch_size rows accumulate, the writer commits them."""
    repo, engine = await _make_repo(tmp_path, flush_batch_size=5)
    await repo.start()
    try:
        for i in range(5):
            await repo.insert(_inv(f"t{i}"))
        # Poll until the batch lands (avoid a fixed sleep).
        deadline = asyncio.get_event_loop().time() + 3.0
        rows: list = []
        while asyncio.get_event_loop().time() < deadline:
            rows = await repo.query(limit=100)
            if len(rows) >= 5:
                break
            await asyncio.sleep(0.02)
        assert len(rows) == 5, f"expected 5 rows flushed by batch size, got {len(rows)}"
    finally:
        await repo.stop()
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_single_row_flushes_without_waiting_for_a_batch(tmp_path):
    """A partial batch (< flush_batch_size) is committed as soon as it arrives."""
    repo, engine = await _make_repo(tmp_path, flush_batch_size=100)
    await repo.start()
    try:
        await repo.insert(_inv("solo"))
        deadline = asyncio.get_event_loop().time() + 3.0
        rows: list = []
        while asyncio.get_event_loop().time() < deadline:
            rows = await repo.query(limit=100)
            if rows:
                break
            await asyncio.sleep(0.02)
        assert len(rows) == 1, "a single row must flush without waiting for a full batch"
    finally:
        await repo.stop()
        await engine.dispose()


@pytest.mark.asyncio
async def test_stop_drains_pending_rows_without_loss(tmp_path):
    """The shutdown-loss case: stop() must persist every queued row.

    Use a large batch so the burst is still queued when stop() runs, then
    assert stop() drained all of it.
    """
    repo, engine = await _make_repo(tmp_path, flush_batch_size=1000)
    await repo.start()
    try:
        for i in range(37):
            await repo.insert(_inv(f"k{i}"))
        await repo.stop()
        rows = await repo.query(limit=1000)
        assert len(rows) == 37, f"stop() lost rows: persisted {len(rows)}/37"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_read_right_after_an_insert_sees_the_row(tmp_path):
    """A read waits for the rows enqueued before it, however slow the commit.

    The gateway records a call and an agent (or a person on the Activity page)
    may look at the log at once; the buffer must not make that call invisible.
    """
    repo, engine = await _make_repo(tmp_path)
    commit = repo._commit_batch

    async def slow_commit(batch):
        await asyncio.sleep(0.3)
        await commit(batch)

    repo._commit_batch = slow_commit  # type: ignore[method-assign]
    await repo.start()
    try:
        await repo.insert(_inv("just-called"))
        rows = await repo.query(limit=10)
        assert [r.capability_key for r in rows] == ["just-called"]
        assert await repo.count() == 1
    finally:
        await repo.stop()
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_read_does_not_hang_on_a_stuck_commit(tmp_path):
    """The wait is bounded: a commit that never finishes slows a read, never hangs it."""
    repo, engine = await _make_repo(tmp_path)
    repo.SETTLE_TIMEOUT_S = 0.1  # type: ignore[misc]
    stuck = asyncio.Event()

    async def stuck_commit(batch):
        await stuck.wait()

    repo._commit_batch = stuck_commit  # type: ignore[method-assign]
    await repo.start()
    try:
        await repo.insert(_inv("never-lands"))
        assert await asyncio.wait_for(repo.query(limit=10), timeout=2.0) == []
    finally:
        stuck.set()
        await repo.stop()
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_idle_writer_sleeps_on_the_queue_and_stops_at_once(tmp_path):
    """With nothing queued the writer waits on the queue with no timer, and
    stop() wakes it straight away instead of waiting for a tick."""
    repo, engine = await _make_repo(tmp_path)
    await repo.start()
    try:
        await asyncio.sleep(0.05)
        task = repo._writer_task
        assert task is not None and not task.done()
        started = asyncio.get_running_loop().time()
        await repo.stop()
        assert asyncio.get_running_loop().time() - started < 0.5
        assert task.done() and not task.cancelled()
    finally:
        await engine.dispose()
