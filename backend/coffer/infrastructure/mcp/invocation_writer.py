"""MCP invocation log: model + buffered writer repo.

Extracted from ``persistence.py`` to keep that module under the 400-line
guideline. ``persistence.py`` re-exports the public names so existing
imports continue to work.

CODE-020: the original implementation committed once per ``insert`` call.
On a tool-call-heavy session that hot-path can dominate request latency
against SQLite (each commit triggers an fsync). The repo here buffers rows
in an in-memory queue drained by a small writer task that flushes either
every ``flush_interval_seconds`` or once ``flush_batch_size`` rows
accumulate — whichever fires first. The writer is owned by the composition
root (``app.py``) which calls ``start()`` on startup and ``stop()`` on
shutdown to drain the queue cleanly.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import TIMESTAMP, Index, Integer, String, Text, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.mcp.capability import MCPInvocation
from coffer.infrastructure.persistence.base import Base


class MCPInvocationModel(Base):
    __tablename__ = "mcp_invocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    resource_name: Mapped[str] = mapped_column(String, nullable=False)
    capability_type: Mapped[str] = mapped_column(String, nullable=False)
    capability_key: Mapped[str] = mapped_column(String, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("idx_invocations_resource", "resource_name", "timestamp"),
        Index("idx_invocations_time", "timestamp"),
        Index("idx_invocations_session", "session_id", "timestamp"),
    )


def _tz(dt: datetime) -> datetime:
    """Re-attach UTC if SQLite stripped the tzinfo on read-back."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _inv_to_domain(row: MCPInvocationModel) -> MCPInvocation:
    return MCPInvocation(
        id=row.id,
        timestamp=_tz(row.timestamp),
        resource_name=row.resource_name,
        capability_type=row.capability_type,  # type: ignore[arg-type]
        capability_key=row.capability_key,
        duration_ms=row.duration_ms,
        status=row.status,  # type: ignore[arg-type]
        error_message=row.error_message,
        session_id=row.session_id,
    )


def _inv_to_model(inv: MCPInvocation) -> MCPInvocationModel:
    return MCPInvocationModel(
        timestamp=inv.timestamp,
        resource_name=inv.resource_name,
        capability_type=inv.capability_type,
        capability_key=inv.capability_key,
        duration_ms=inv.duration_ms,
        status=inv.status,
        error_message=inv.error_message,
        session_id=inv.session_id,
    )


class MCPInvocationRepo:
    """Buffered writer for the MCP invocation log.

    The public ``insert`` API stays an ``async def`` so the call sites in
    ``gateway_handlers`` need no changes; it just enqueues and returns.
    """

    DEFAULT_QUEUE_MAX = 5000
    DEFAULT_BATCH_SIZE = 50
    DEFAULT_FLUSH_INTERVAL_S = 0.05

    def __init__(
        self,
        sm: async_sessionmaker,  # type: ignore[type-arg]
        *,
        queue_max: int = DEFAULT_QUEUE_MAX,
        flush_batch_size: int = DEFAULT_BATCH_SIZE,
        flush_interval_seconds: float = DEFAULT_FLUSH_INTERVAL_S,
    ) -> None:
        self._sm = sm
        self._queue_max = queue_max
        self._flush_batch_size = flush_batch_size
        self._flush_interval = flush_interval_seconds
        self._queue: asyncio.Queue[MCPInvocation] | None = None
        self._writer_task: asyncio.Task[None] | None = None
        self._stopping = False

    # --- lifecycle (called by composition root) -------------------------- #

    async def start(self) -> None:
        if self._writer_task is not None:
            return
        self._queue = asyncio.Queue(maxsize=self._queue_max)
        self._stopping = False
        self._writer_task = asyncio.create_task(self._run(), name="mcp-invocation-writer")

    async def stop(self) -> None:
        """Drain remaining rows and stop the writer task."""
        if self._writer_task is None:
            return
        self._stopping = True
        # The writer loop wakes up on its own interval; cancelling would lose
        # buffered rows. Wait for the task to drain naturally on next tick.
        # We bound the wait so shutdown can't hang on a stuck DB.
        try:
            await asyncio.wait_for(self._writer_task, timeout=5.0)
        except TimeoutError:
            self._writer_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._writer_task
        self._writer_task = None
        self._queue = None

    # --- public API ------------------------------------------------------ #

    async def insert(self, inv: MCPInvocation) -> None:
        """Enqueue (when a writer is running) or commit synchronously."""
        if self._queue is None:
            # No writer: fall back to immediate commit. Used in tests and in
            # any code path that exercises the repo before start() has been
            # called by the composition root.
            await self._commit_one(inv)
            return
        try:
            self._queue.put_nowait(inv)
        except asyncio.QueueFull:
            # The queue is sized far beyond any reasonable burst; if it's
            # full we'd rather block briefly than drop audit rows.
            await self._queue.put(inv)

    async def query(
        self,
        *,
        resource_name: str | None = None,
        status: Literal["ok", "error", "timeout", "denied"] | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[MCPInvocation]:
        async with self._sm() as session:
            stmt = select(MCPInvocationModel).order_by(MCPInvocationModel.timestamp.desc())
            if resource_name is not None:
                stmt = stmt.where(MCPInvocationModel.resource_name == resource_name)
            if status is not None:
                stmt = stmt.where(MCPInvocationModel.status == status)
            if since is not None:
                stmt = stmt.where(MCPInvocationModel.timestamp >= since)
            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_inv_to_domain(r) for r in rows]

    # --- internals ------------------------------------------------------- #

    async def _commit_one(self, inv: MCPInvocation) -> None:
        async with self._sm() as session:
            session.add(_inv_to_model(inv))
            await session.commit()

    async def _commit_batch(self, batch: list[MCPInvocation]) -> None:
        if not batch:
            return
        async with self._sm() as session:
            session.add_all([_inv_to_model(inv) for inv in batch])
            await session.commit()

    async def _run(self) -> None:
        assert self._queue is not None
        queue = self._queue
        while True:
            batch: list[MCPInvocation] = []
            try:
                first = await asyncio.wait_for(queue.get(), timeout=self._flush_interval)
                batch.append(first)
            except TimeoutError:
                if self._stopping and queue.empty():
                    return
                continue
            except asyncio.CancelledError:
                # Best-effort drain on cancel.
                while not queue.empty():
                    batch.append(queue.get_nowait())
                with suppress(Exception):
                    await self._commit_batch(batch)
                raise
            # Greedily pull up to batch_size-1 more without waiting.
            while len(batch) < self._flush_batch_size and not queue.empty():
                batch.append(queue.get_nowait())
            try:
                await self._commit_batch(batch)
            except Exception:
                # Persistent DB failure shouldn't crash the writer; log and
                # carry on. We do NOT requeue: better to drop one batch than
                # to pin memory growing forever.
                import logging

                logging.getLogger(__name__).exception(
                    "mcp.invocation_writer.commit_failed",
                    extra={"batch_size": len(batch)},
                )
            if self._stopping and queue.empty():
                return
