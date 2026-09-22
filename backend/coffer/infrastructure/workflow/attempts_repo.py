"""The attempt repository — one try at one node.

Split out of :mod:`repository` for the file-size cap, the same way the approval
repository was. The seam is the table.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.infrastructure.workflow.models import WorkflowNodeAttemptModel

__all__ = ["WorkflowAttemptRepo"]


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC)


class WorkflowAttemptRepo:
    """One row per try at a node. A retry inserts; it never rewrites (FR-022)."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def insert_attempt(
        self,
        *,
        attempt_id: str,
        run_id: str,
        stage_key: str,
        node_key: str,
        attempt: int,
        status: str = "pending",
        conversation_id: str | None = None,
        instructions: str | None = None,
        started_at: datetime | None = None,
    ) -> WorkflowNodeAttemptModel:
        """Insert attempt ``attempt`` of ``node_key``.

        ``(run_id, node_key, attempt)`` is unique, so a second insert of the
        same attempt number raises rather than forking the history of a node.
        """
        row = WorkflowNodeAttemptModel(
            id=attempt_id,
            run_id=run_id,
            stage_key=stage_key,
            node_key=node_key,
            attempt=attempt,
            status=status,
            conversation_id=conversation_id,
            instructions=instructions,
            tokens=0,
            started_at=started_at,
        )
        async with self._sm() as session:
            session.add(row)
            await session.commit()
        return row

    async def update_attempt(
        self,
        attempt_id: str,
        *,
        status: str | None = None,
        conversation_id: str | None = None,
        summary: str | None = None,
        failure_reason: str | None = None,
        instructions: str | None = None,
        tokens: int | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> WorkflowNodeAttemptModel | None:
        """Move an attempt forward. ``None`` leaves a field as it is.

        There is deliberately no way to clear a field back to NULL: an attempt
        only moves forward — it acquires a conversation, a summary, a reason it
        failed, another line of what the developer told it — and a retry that
        wants a clean slate gets a new row, not this one blanked.
        """
        values: dict[str, Any] = {}
        for column, value in (
            ("status", status),
            ("conversation_id", conversation_id),
            ("summary", summary),
            ("failure_reason", failure_reason),
            ("instructions", instructions),
            ("tokens", tokens),
            ("started_at", started_at),
            ("finished_at", finished_at),
        ):
            if value is not None:
                values[column] = value
        async with self._sm() as session:
            if values:
                await session.execute(
                    update(WorkflowNodeAttemptModel)
                    .where(WorkflowNodeAttemptModel.id == attempt_id)
                    .values(**values)
                )
                await session.commit()
            stmt = select(WorkflowNodeAttemptModel).where(WorkflowNodeAttemptModel.id == attempt_id)
            row: WorkflowNodeAttemptModel | None = (
                await session.execute(stmt)
            ).scalar_one_or_none()
            return row

    async def set_assignment(
        self,
        attempt_id: str,
        *,
        agent: str | None,
        model: str | None,
        effort: str | None,
    ) -> WorkflowNodeAttemptModel | None:
        """Write who runs this attempt, on what, at what effort (FR-071).

        Its own method rather than three more arguments on ``update_attempt``,
        because it writes all three VERBATIM: ``None`` here means "clear it,
        fall back to the template", which is the opposite of what ``None``
        means there. Clearing an override has to be possible — the developer
        who picked the bigger model for a task that has not started yet must be
        able to change their mind before it does.
        """
        async with self._sm() as session:
            await session.execute(
                update(WorkflowNodeAttemptModel)
                .where(WorkflowNodeAttemptModel.id == attempt_id)
                .values(agent=agent, model=model, effort=effort)
            )
            await session.commit()
            stmt = select(WorkflowNodeAttemptModel).where(WorkflowNodeAttemptModel.id == attempt_id)
            row: WorkflowNodeAttemptModel | None = (
                await session.execute(stmt)
            ).scalar_one_or_none()
            return row

    async def latest_attempt(self, run_id: str, node_key: str) -> WorkflowNodeAttemptModel | None:
        """The highest-numbered attempt at a node — the one that counts now."""
        async with self._sm() as session:
            stmt = (
                select(WorkflowNodeAttemptModel)
                .where(
                    WorkflowNodeAttemptModel.run_id == run_id,
                    WorkflowNodeAttemptModel.node_key == node_key,
                )
                .order_by(WorkflowNodeAttemptModel.attempt.desc())
                .limit(1)
            )
            row: WorkflowNodeAttemptModel | None = (
                await session.execute(stmt)
            ).scalar_one_or_none()
            return row

    async def attempt_by_conversation(
        self, conversation_id: str
    ) -> WorkflowNodeAttemptModel | None:
        """The attempt whose work happens in this conversation, if any.

        This is what lets a tool call be attributed to a run after a daemon
        restart. The run identity a node's agent reports is set from the
        environment when its turn starts, so it has to be derivable from the
        conversation alone — an in-memory map built when the conversation was
        created would be empty after a restart, and the next turn on that same
        conversation (a node in review being given feedback) would run ungated.
        A conversation with no attempt is an ordinary conversation and gets no
        run identity, which is the whole point.
        """
        async with self._sm() as session:
            stmt = (
                select(WorkflowNodeAttemptModel)
                .where(WorkflowNodeAttemptModel.conversation_id == conversation_id)
                .order_by(WorkflowNodeAttemptModel.attempt.desc())
                .limit(1)
            )
            row: WorkflowNodeAttemptModel | None = (
                await session.execute(stmt)
            ).scalar_one_or_none()
            return row

    async def list_attempts(self, run_id: str) -> list[WorkflowNodeAttemptModel]:
        """Every attempt in the run, oldest first — what a run view renders."""
        async with self._sm() as session:
            stmt = (
                select(WorkflowNodeAttemptModel)
                .where(WorkflowNodeAttemptModel.run_id == run_id)
                .order_by(
                    WorkflowNodeAttemptModel.node_key,
                    WorkflowNodeAttemptModel.attempt,
                )
            )
            return list((await session.execute(stmt)).scalars().all())
