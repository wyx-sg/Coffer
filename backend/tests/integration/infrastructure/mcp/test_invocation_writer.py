"""Buffered-writer coverage for MCPInvocationRepo (CODE-020).

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
        resource_name="fs",
        capability_type="tool",
        capability_key=key,
        duration_ms=1,
        status="ok",
    )


@pytest.mark.asyncio
async def test_buffered_insert_flushes_by_batch_size(tmp_path):
    """Once flush_batch_size rows accumulate, the writer commits them."""
    repo, engine = await _make_repo(tmp_path, flush_batch_size=5, flush_interval_seconds=10.0)
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
async def test_buffered_insert_flushes_by_interval(tmp_path):
    """A partial batch (< flush_batch_size) still flushes on the interval tick."""
    repo, engine = await _make_repo(tmp_path, flush_batch_size=100, flush_interval_seconds=0.05)
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
        assert len(rows) == 1, "a single row must flush on the interval tick"
    finally:
        await repo.stop()
        await engine.dispose()


@pytest.mark.asyncio
async def test_stop_drains_pending_rows_without_loss(tmp_path):
    """The shutdown-loss case: stop() must persist every queued row.

    Use a long interval and large batch so nothing flushes before stop(), then
    assert stop() drained the full burst.
    """
    repo, engine = await _make_repo(tmp_path, flush_batch_size=1000, flush_interval_seconds=10.0)
    await repo.start()
    try:
        for i in range(37):
            await repo.insert(_inv(f"k{i}"))
        # Nothing should have flushed yet (batch not reached, interval not hit).
        await repo.stop()
        rows = await repo.query(limit=1000)
        assert len(rows) == 37, f"stop() lost rows: persisted {len(rows)}/37"
    finally:
        await engine.dispose()
