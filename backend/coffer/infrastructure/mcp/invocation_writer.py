"""MCP invocation log: model + buffered writer repo.

Extracted from ``persistence.py`` to keep that module under the 400-line
guideline. ``persistence.py`` re-exports the public names so existing
imports continue to work.

The original implementation committed once per ``insert`` call.
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
from typing import Any, Literal

from sqlalchemy import TIMESTAMP, Index, Integer, Select, String, Text, case, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.mcp.capability import MCPInvocation
from coffer.infrastructure.mcp.invocation_summary import InvocationSummary, summarize
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.keyset import newest_first_after
from coffer.infrastructure.persistence.models import ResourceModel


class MCPInvocationModel(Base):
    __tablename__ = "mcp_invocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    #: WHICH server, by identity (migration 0097). The log is history, so it has
    #: to survive the rename that a name-keyed column would have split it across.
    #: Not a foreign key: a deleted server's invocations stay readable, and two
    #: reserved non-uid values live here — see ``domain.mcp.capability``.
    resource_uid: Mapped[str] = mapped_column(String, nullable=False)
    capability_type: Mapped[str] = mapped_column(String, nullable=False)
    capability_key: Mapped[str] = mapped_column(String, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    #: The calling agent's uid, as its session reported it (migration 0110).
    #: Not a foreign key, for the same reason ``resource_uid`` is not one: a
    #: deleted agent's calls stay in the history.
    agent_uid: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("idx_invocations_resource", "resource_uid", "timestamp"),
        Index("idx_invocations_time", "timestamp"),
        Index("idx_invocations_session", "session_id", "timestamp"),
        Index("idx_invocations_agent", "agent_uid", "timestamp"),
    )


def _tz(dt: datetime) -> datetime:
    """Re-attach UTC if SQLite stripped the tzinfo on read-back."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _filtered(
    stmt: Select[Any],
    *,
    resource_uid: str | None,
    status: str | None,
    since: datetime | None,
    agent_uid: str | None,
) -> Select[Any]:
    """The one WHERE both the page and its count read, so they cannot disagree."""
    if resource_uid is not None:
        stmt = stmt.where(MCPInvocationModel.resource_uid == resource_uid)
    if status is not None:
        stmt = stmt.where(MCPInvocationModel.status == status)
    if since is not None:
        stmt = stmt.where(MCPInvocationModel.timestamp >= since)
    if agent_uid is not None:
        stmt = stmt.where(MCPInvocationModel.agent_uid == agent_uid)
    return stmt


def _inv_to_domain(row: MCPInvocationModel) -> MCPInvocation:
    return MCPInvocation(
        id=row.id,
        timestamp=_tz(row.timestamp),
        resource_uid=row.resource_uid,
        capability_type=row.capability_type,  # type: ignore[arg-type]
        capability_key=row.capability_key,
        duration_ms=row.duration_ms,
        status=row.status,  # type: ignore[arg-type]
        error_message=row.error_message,
        session_id=row.session_id,
        agent_uid=row.agent_uid,
    )


def _inv_to_model(inv: MCPInvocation) -> MCPInvocationModel:
    return MCPInvocationModel(
        timestamp=inv.timestamp,
        resource_uid=inv.resource_uid,
        capability_type=inv.capability_type,
        capability_key=inv.capability_key,
        duration_ms=inv.duration_ms,
        status=inv.status,
        error_message=inv.error_message,
        session_id=inv.session_id,
        agent_uid=inv.agent_uid,
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
        resource_uid: str | None = None,
        status: Literal["ok", "error", "timeout", "denied"] | None = None,
        since: datetime | None = None,
        agent_uid: str | None = None,
        limit: int = 50,
        after: tuple[datetime, int] | None = None,
    ) -> list[MCPInvocation]:
        async with self._sm() as session:
            # Newest first, the id breaking ties, so ``after`` (the previous
            # page's last row) names one place in the order.
            stmt = select(MCPInvocationModel).order_by(
                MCPInvocationModel.timestamp.desc(), MCPInvocationModel.id.desc()
            )
            if after is not None:
                stmt = stmt.where(
                    newest_first_after(MCPInvocationModel.timestamp, MCPInvocationModel.id, after)
                )
            stmt = _filtered(
                stmt, resource_uid=resource_uid, status=status, since=since, agent_uid=agent_uid
            )
            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_inv_to_domain(r) for r in rows]

    async def count(
        self,
        *,
        resource_uid: str | None = None,
        status: Literal["ok", "error", "timeout", "denied"] | None = None,
        since: datetime | None = None,
        agent_uid: str | None = None,
    ) -> int:
        """How many rows match these filters across every page (no cursor)."""
        async with self._sm() as session:
            stmt = _filtered(
                select(func.count()).select_from(MCPInvocationModel),
                resource_uid=resource_uid,
                status=status,
                since=since,
                agent_uid=agent_uid,
            )
            return int((await session.execute(stmt)).scalar_one())

    async def usage_counts(
        self,
        *,
        since: datetime,
    ) -> dict[tuple[str, str], int]:
        """Tool-invocation counts per (server NAME, tool) at or after ``since``.

        The ranking signal for tool tiering. Every status counts — an
        errored call still proves the agent reached for that tool, and demoting
        a tool because its upstream was flaky would hide it exactly when the
        user is trying to get it working.

        Rows are STORED by uid and come back keyed by name, and the join that
        turns one into the other belongs here rather than in the caller: the
        only consumer is the tiering policy, which ranks the namespaced wire
        names (``<server>__<tool>``) of an aggregated ``tools/list``, and that
        namespace is the label. Doing it in SQL also means the counts already
        answer to the server's CURRENT name — the history a rename used to split
        in two now ranks as one server, which is the behaviour a user would
        expect and never got.

        An inner join, so rows that resolve to no resource simply do not appear:
        Coffer's own built-ins (which never enter tiering — they are listed
        unconditionally and outside the budget) and servers deleted before the
        window closed (whose tools are not in the catalogue being ranked). No
        count is attributed to the wrong server, and nothing is hidden by their
        absence — tiering only ever decides an ORDER among tools that exist.
        """
        async with self._sm() as session:
            stmt = (
                select(
                    ResourceModel.name,
                    MCPInvocationModel.capability_key,
                    func.count().label("n"),
                )
                .join(ResourceModel, ResourceModel.uid == MCPInvocationModel.resource_uid)
                .where(MCPInvocationModel.capability_type == "tool")
                .where(MCPInvocationModel.timestamp >= since)
                .group_by(
                    ResourceModel.name,
                    MCPInvocationModel.capability_key,
                )
            )
            rows = (await session.execute(stmt)).all()
        return {(r.name, r.capability_key): int(r.n) for r in rows}

    async def summary(self, *, resource_uid: str, since: datetime) -> InvocationSummary:
        """One server's call counts since ``since`` (``invocation_summary``)."""
        return await summarize(self._sm, MCPInvocationModel, resource_uid=resource_uid, since=since)

    # --- internals ------------------------------------------------------- #

    async def tool_outcomes(
        self, *, resource_uids: list[str], since: datetime
    ) -> dict[str, dict[str, tuple[int, int]]]:
        """``{server uid: {tool: (calls, failures)}}`` at or after ``since``.

        The custom tools page's 24-hour summary (spec mcp-gateway "Manage
        custom tools on REST and the command line"). A failure is an ``error``
        or a ``timeout``; a ``denied`` call is counted as a call only.
        """
        if not resource_uids:
            return {}
        failed = case((MCPInvocationModel.status.in_(("error", "timeout")), 1), else_=0)
        async with self._sm() as session:
            stmt = (
                select(
                    MCPInvocationModel.resource_uid,
                    MCPInvocationModel.capability_key,
                    func.count().label("n"),
                    func.sum(failed).label("f"),
                )
                .where(MCPInvocationModel.capability_type == "tool")
                .where(MCPInvocationModel.resource_uid.in_(resource_uids))
                .where(MCPInvocationModel.timestamp >= since)
                .group_by(MCPInvocationModel.resource_uid, MCPInvocationModel.capability_key)
            )
            rows = (await session.execute(stmt)).all()
        out: dict[str, dict[str, tuple[int, int]]] = {}
        for r in rows:
            out.setdefault(r.resource_uid, {})[r.capability_key] = (int(r.n), int(r.f or 0))
        return out

    async def last_tool_call(self, resource_uid: str, *, since: datetime) -> MCPInvocation | None:
        """The newest tool call on one server at or after ``since`` that
        reached it (a ``denied`` call never did)."""
        async with self._sm() as session:
            stmt = (
                select(MCPInvocationModel)
                .where(MCPInvocationModel.resource_uid == resource_uid)
                .where(MCPInvocationModel.capability_type == "tool")
                .where(MCPInvocationModel.status != "denied")
                .where(MCPInvocationModel.timestamp >= since)
                .order_by(MCPInvocationModel.timestamp.desc(), MCPInvocationModel.id.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        return _inv_to_domain(row) if row is not None else None

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
