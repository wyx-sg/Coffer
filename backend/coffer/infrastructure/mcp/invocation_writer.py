"""MCP invocation log: model + buffered writer repo.

Extracted from ``persistence.py`` (which re-exports the public names) for the
400-line guideline. Committing once per ``insert`` let a tool-call-heavy
session's fsyncs dominate request latency, so the repo here buffers rows
in an in-memory queue drained by a small writer task that flushes either
every ``flush_interval_seconds`` or once ``flush_batch_size`` rows
accumulate — whichever fires first. The writer is owned by the composition
root (``app.py``) which calls ``start()`` on startup and ``stop()`` on
shutdown to drain the queue cleanly.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import datetime
from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.runtime.supervisor import spawn
from coffer.domain.mcp.capability import MCPInvocation
from coffer.infrastructure.mcp.invocation_rows import (
    MCPInvocationModel,
    filtered,
    inv_to_domain,
    inv_to_model,
)
from coffer.infrastructure.mcp.invocation_summary import InvocationSummary, summarize
from coffer.infrastructure.persistence.keyset import newest_first_after

_logger = logging.getLogger(__name__)


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
        name_of: Callable[[str], str | None] = lambda _uid: None,
    ) -> None:
        self._sm = sm
        # uid -> the server's current name (the resource store's), for
        # ``usage_counts``: resources are files now, so the join is here.
        self._name_of = name_of
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
        self._writer_task = spawn(self._run(), name="mcp-invocation-writer")

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
        status: Literal["ok", "error", "timeout", "denied", "failed"] | None = None,
        since: datetime | None = None,
        agent_uid: str | None = None,
        limit: int = 50,
        after: tuple[datetime, int] | None = None,
        trace_id: str | None = None,
        q: str | None = None,
        q_resource_uids: Sequence[str] = (),
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
            stmt = filtered(
                stmt,
                resource_uid=resource_uid,
                status=status,
                since=since,
                agent_uid=agent_uid,
                trace_id=trace_id,
                q=q,
                q_resource_uids=q_resource_uids,
            )
            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [inv_to_domain(r) for r in rows]

    async def count(
        self,
        *,
        resource_uid: str | None = None,
        status: Literal["ok", "error", "timeout", "denied", "failed"] | None = None,
        since: datetime | None = None,
        agent_uid: str | None = None,
        trace_id: str | None = None,
        q: str | None = None,
        q_resource_uids: Sequence[str] = (),
    ) -> int:
        """How many rows match these filters across every page (no cursor)."""
        async with self._sm() as session:
            stmt = filtered(
                select(func.count()).select_from(MCPInvocationModel),
                resource_uid=resource_uid,
                status=status,
                since=since,
                agent_uid=agent_uid,
                trace_id=trace_id,
                q=q,
                q_resource_uids=q_resource_uids,
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
        namespace is the label. Resolving through the uid also means the counts
        answer to the server's CURRENT name — the history a rename used to split
        in two now ranks as one server, which is the behaviour a user would
        expect and never got.

        Rows whose uid resolves to no resource simply do not appear:
        Coffer's own built-ins (which never enter tiering — they are listed
        unconditionally and outside the budget) and servers deleted before the
        window closed (whose tools are not in the catalogue being ranked). No
        count is attributed to the wrong server, and nothing is hidden by their
        absence — tiering only ever decides an ORDER among tools that exist.
        """
        async with self._sm() as session:
            stmt = (
                select(
                    MCPInvocationModel.resource_uid,
                    MCPInvocationModel.capability_key,
                    func.count().label("n"),
                )
                .where(MCPInvocationModel.capability_type == "tool")
                .where(MCPInvocationModel.timestamp >= since)
                .group_by(MCPInvocationModel.resource_uid, MCPInvocationModel.capability_key)
            )
            rows = (await session.execute(stmt)).all()
        out: dict[tuple[str, str], int] = {}
        for r in rows:
            name = self._name_of(r.resource_uid)
            if name is not None:
                key = (name, r.capability_key)
                out[key] = out.get(key, 0) + int(r.n)
        return out

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
        return inv_to_domain(row) if row is not None else None

    async def _commit_one(self, inv: MCPInvocation) -> None:
        async with self._sm() as session:
            session.add(inv_to_model(inv))
            await session.commit()

    async def _commit_batch(self, batch: list[MCPInvocation]) -> None:
        if not batch:
            return
        async with self._sm() as session:
            session.add_all([inv_to_model(inv) for inv in batch])
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
                _logger.exception(
                    "mcp.invocation_writer.commit_failed", extra={"batch_size": len(batch)}
                )
            if self._stopping and queue.empty():
                return
