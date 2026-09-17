"""Concrete repositories over the four workflow tables.

Four small classes rather than one: a run's projection, its event log, its
attempts and its approvals are written by different callers at different
moments, and the one thing they share — the session maker — is passed in.

These are concrete classes, not implementations of a Protocol: the
application layer does not exist yet, and when it does it will define its
ports against these method names rather than the other way round.

Rows in, rows out. The repositories return their ORM models and the
application layer maps them to ``domain.workflow.run`` entities, because the
mapping is a decision about vocabulary (which enum a TEXT column means) and
this layer's job is the storage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.workflow.run import RunProjection
from coffer.infrastructure.workflow.approvals_repo import (
    WorkflowApprovalRepo,  # re-export (split out for the file-size budget)
)
from coffer.infrastructure.workflow.attempts_repo import WorkflowAttemptRepo
from coffer.infrastructure.workflow.models import (
    WorkflowEventModel,
    WorkflowRunModel,
)

__all__ = [
    "RunProjection",
    "WorkflowApprovalRepo",
    "WorkflowAttemptRepo",
    "WorkflowEventRepo",
    "WorkflowRunRepo",
]


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC)


class WorkflowRunRepo:
    """The ``workflow_runs`` row: created once, then advanced under a version."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def create_run(
        self,
        *,
        run_id: str,
        title: str,
        workdir: str,
        machine_id: str,
        template_snapshot: dict[str, Any],
        template_ref: str | None = None,
        status: str = "draft",
        inputs: list[Any] | None = None,
        now: datetime | None = None,
    ) -> WorkflowRunModel:
        """Insert a run at version 1, carrying its frozen snapshot (FR-010)."""
        stamp = _now(now)
        row = WorkflowRunModel(
            id=run_id,
            template_ref=template_ref,
            template_snapshot=template_snapshot,
            title=title,
            workdir=workdir,
            machine_id=machine_id,
            status=status,
            version=1,
            tokens_spent=0,
            inputs=inputs if inputs is not None else [],
            created_at=stamp,
            updated_at=stamp,
        )
        async with self._sm() as session:
            session.add(row)
            await session.commit()
        return row

    async def get_run(self, run_id: str) -> WorkflowRunModel | None:
        async with self._sm() as session:
            stmt = select(WorkflowRunModel).where(WorkflowRunModel.id == run_id)
            row: WorkflowRunModel | None = (await session.execute(stmt)).scalar_one_or_none()
            return row

    async def list_runs(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[WorkflowRunModel]:
        """Newest activity first.

        Ordered by ``updated_at`` and then by ``id``, because ``updated_at``
        alone is not a total order — two runs advanced in the same
        transaction would be free to trade places between two reads of the
        list, and a user clicking a row in it would hit whichever one moved.
        """
        async with self._sm() as session:
            stmt = select(WorkflowRunModel)
            if status is not None:
                stmt = stmt.where(WorkflowRunModel.status == status)
            stmt = stmt.order_by(WorkflowRunModel.updated_at.desc(), WorkflowRunModel.id)
            if limit is not None:
                stmt = stmt.limit(limit)
            return list((await session.execute(stmt)).scalars().all())

    async def update_run_projection(
        self,
        run_id: str,
        expected_version: int,
        projection: RunProjection,
        *,
        now: datetime | None = None,
    ) -> WorkflowRunModel | None:
        """Advance the projection, or refuse a stale caller (FR-015).

        Returns the updated row, or ``None`` when ``expected_version`` is not
        the version on disk — the caller turns that into
        ``WorkflowVersionConflict`` with the current version and position,
        which it gets by reading the run back.

        The check is the UPDATE's own WHERE clause, not a read followed by a
        write: between a SELECT and an UPDATE two callers can both observe
        version 4, both find it current and both apply, which is precisely the
        lost update the version exists to prevent.
        """
        stmt = (
            update(WorkflowRunModel)
            .where(
                WorkflowRunModel.id == run_id,
                WorkflowRunModel.version == expected_version,
            )
            .values(
                status=projection.status,
                current_stage_key=projection.current_stage_key,
                current_node_key=projection.current_node_key,
                tokens_spent=projection.tokens_spent,
                version=expected_version + 1,
                updated_at=_now(now),
            )
        )
        async with self._sm() as session:
            result = await session.execute(stmt)
            if result.rowcount == 0:
                await session.rollback()
                return None
            await session.commit()
            refreshed = select(WorkflowRunModel).where(WorkflowRunModel.id == run_id)
            row: WorkflowRunModel | None = (await session.execute(refreshed)).scalar_one_or_none()
            return row

    async def set_inputs(
        self,
        run_id: str,
        inputs: list[Any],
        *,
        now: datetime | None = None,
    ) -> WorkflowRunModel | None:
        """Replace the run's mounted inputs (FR-050).

        No version predicate and no version bump. Mounting a PRD or unmounting
        a stale collection does not advance the run — it changes what the NEXT
        node opens with — so it is deliberately outside the optimistic-lock
        cycle that guards the run's position. ``updated_at`` still moves,
        because the run list is ordered by it and a run the developer just
        touched belongs at the top.
        """
        stmt = (
            update(WorkflowRunModel)
            .where(WorkflowRunModel.id == run_id)
            .values(inputs=list(inputs), updated_at=_now(now))
        )
        async with self._sm() as session:
            result = await session.execute(stmt)
            if result.rowcount == 0:
                await session.rollback()
                return None
            await session.commit()
            refreshed = select(WorkflowRunModel).where(WorkflowRunModel.id == run_id)
            row: WorkflowRunModel | None = (await session.execute(refreshed)).scalar_one_or_none()
            return row

    async def delete_run(self, run_id: str) -> None:
        """Delete the run; its events, attempts and approvals go with it.

        One statement, because the cascade is the schema's (`ON DELETE CASCADE`
        with `PRAGMA foreign_keys = ON`) rather than four DELETEs this method
        would have to keep in step with the tables. Deleting a run that is
        already gone is silent: the caller asked for it to be absent, and it is.
        """
        async with self._sm() as session:
            await session.execute(delete(WorkflowRunModel).where(WorkflowRunModel.id == run_id))
            await session.commit()


class WorkflowEventRepo:
    """The append-only log. Nothing here updates or deletes."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def append_event(
        self,
        *,
        event_id: str,
        run_id: str,
        event_type: str,
        actor: dict[str, Any],
        stage_key: str | None = None,
        node_key: str | None = None,
        payload: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> WorkflowEventModel:
        """Append one event, assigning the next sequence for the run.

        How the sequence is assigned: by a correlated ``SELECT MAX(sequence)``
        **inside the INSERT statement itself**, so the read and the write are
        one statement and no second appender can slip between them. The
        alternative — read the max, then insert — leaves a window in which two
        appenders both compute the same next number; the unique constraint
        would catch it, but only as an error the caller has to retry, and a
        retry loop is a worse thing to own than a subquery.
        """
        next_sequence = (
            select(func.coalesce(func.max(WorkflowEventModel.sequence), 0) + 1)
            .where(WorkflowEventModel.run_id == run_id)
            .scalar_subquery()
        )
        stmt = insert(WorkflowEventModel).values(
            id=event_id,
            run_id=run_id,
            sequence=next_sequence,
            event_type=event_type,
            actor=actor,
            stage_key=stage_key,
            node_key=node_key,
            payload=payload if payload is not None else {},
            created_at=_now(now),
        )
        async with self._sm() as session:
            await session.execute(stmt)
            await session.commit()
            written = select(WorkflowEventModel).where(WorkflowEventModel.id == event_id)
            row: WorkflowEventModel = (await session.execute(written)).scalar_one()
            return row

    async def list_events(
        self,
        run_id: str,
        *,
        after_sequence: int | None = None,
        limit: int | None = None,
    ) -> list[WorkflowEventModel]:
        """A run's events in the order they happened.

        ``after_sequence`` is what a surface tailing the log passes to get only
        what it has not seen.
        """
        async with self._sm() as session:
            stmt = select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id)
            if after_sequence is not None:
                stmt = stmt.where(WorkflowEventModel.sequence > after_sequence)
            stmt = stmt.order_by(WorkflowEventModel.sequence)
            if limit is not None:
                stmt = stmt.limit(limit)
            return list((await session.execute(stmt)).scalars().all())
