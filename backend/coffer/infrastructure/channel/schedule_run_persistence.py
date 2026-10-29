"""Channel-kind ORM model + repo for ``scheduled_task_runs``: every run of every
scheduled task (spec channels "Keep every scheduled run in the task's history").

``runs.db`` holds it, beside the other per-chat history, and the retention
worker prunes it by ``started_at``. A run outlives its task — a follow-up is
removed once it has run — so rows carry the task's name as it was. Ids, times
and outcomes only: what the agent said stays in its own session.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import TIMESTAMP, Boolean, Index, String, Text, delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.infrastructure.persistence.base import Base

__all__ = ["RUNS_TABLE", "ScheduledRunModel", "ScheduledRunRepo"]

RUNS_TABLE = "scheduled_task_runs"


class ScheduledRunModel(Base):
    __tablename__ = RUNS_TABLE

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_uid: Mapped[str] = mapped_column(String, nullable=False)
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    channel_uid: Mapped[str] = mapped_column(String, nullable=False)
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    due_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    catch_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trigger: Mapped[str] = mapped_column(String, nullable=False, default="schedule")
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    conversation_id: Mapped[str] = mapped_column(String, nullable=False, default="")

    __table_args__ = (
        Index("idx_scheduled_task_runs_task", "task_uid", "started_at"),
        Index("idx_scheduled_task_runs_started", "started_at"),
    )


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _to_domain(row: ScheduledRunModel) -> ScheduledRun:
    return ScheduledRun(
        run_id=row.run_id,
        task_uid=row.task_uid,
        task_name=row.task_name,
        channel_uid=row.channel_uid,
        chat_id=row.chat_id,
        due_at=_aware(row.due_at) or row.due_at,
        catch_up=bool(row.catch_up),
        trigger="manual" if row.trigger == "manual" else "schedule",
        started_at=_aware(row.started_at) or row.started_at,
        finished_at=_aware(row.finished_at),
        outcome=row.outcome,  # type: ignore[arg-type]
        reason=row.reason or "",
        conversation_id=row.conversation_id or "",
    )


class ScheduledRunRepo:
    """SQLAlchemy implementation of ``ScheduledRunRepoPort``."""

    def __init__(self, session_maker: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = session_maker

    async def add(self, run: ScheduledRun) -> None:
        async with self._sm() as session:
            session.add(
                ScheduledRunModel(
                    run_id=run.run_id,
                    task_uid=run.task_uid,
                    task_name=run.task_name,
                    channel_uid=run.channel_uid,
                    chat_id=run.chat_id,
                    due_at=run.due_at,
                    catch_up=run.catch_up,
                    trigger=run.trigger,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    outcome=run.outcome,
                    reason=run.reason,
                    conversation_id=run.conversation_id,
                )
            )
            await session.commit()

    async def finish(
        self,
        run_id: str,
        *,
        outcome: str,
        reason: str,
        finished_at: datetime,
        conversation_id: str | None = None,
    ) -> None:
        values: dict[str, object] = {
            "outcome": outcome,
            "reason": reason,
            "finished_at": finished_at,
        }
        if conversation_id is not None:
            values["conversation_id"] = conversation_id
        async with self._sm() as session:
            await session.execute(
                update(ScheduledRunModel).where(ScheduledRunModel.run_id == run_id).values(**values)
            )
            await session.commit()

    async def note_conversation(self, run_id: str, conversation_id: str) -> None:
        async with self._sm() as session:
            await session.execute(
                update(ScheduledRunModel)
                .where(ScheduledRunModel.run_id == run_id)
                .values(conversation_id=conversation_id)
            )
            await session.commit()

    async def get(self, run_id: str) -> ScheduledRun | None:
        async with self._sm() as session:
            row = await session.get(ScheduledRunModel, run_id)
            return _to_domain(row) if row is not None else None

    async def latest_slot(self, task_uid: str) -> datetime | None:
        """The newest slot a scheduled (not manual) run was recorded for."""
        async with self._sm() as session:
            value = (
                await session.execute(
                    select(ScheduledRunModel.due_at)
                    .where(
                        ScheduledRunModel.task_uid == task_uid,
                        ScheduledRunModel.trigger == "schedule",
                    )
                    .order_by(ScheduledRunModel.due_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return _aware(value)

    async def for_task(self, task_uid: str, *, limit: int = 50) -> list[ScheduledRun]:
        async with self._sm() as session:
            rows = (
                await session.execute(
                    select(ScheduledRunModel)
                    .where(ScheduledRunModel.task_uid == task_uid)
                    .order_by(ScheduledRunModel.started_at.desc())
                    .limit(limit)
                )
            ).scalars()
            return [_to_domain(r) for r in rows]

    async def latest_for(self, task_uids: Sequence[str]) -> dict[str, ScheduledRun]:
        """Each task's newest run, for the list page."""
        out: dict[str, ScheduledRun] = {}
        if not task_uids:
            return out
        async with self._sm() as session:
            rows = (
                await session.execute(
                    select(ScheduledRunModel)
                    .where(ScheduledRunModel.task_uid.in_(list(task_uids)))
                    .order_by(ScheduledRunModel.started_at.desc())
                )
            ).scalars()
            for row in rows:
                out.setdefault(row.task_uid, _to_domain(row))
        return out

    async def since(self, when: datetime) -> list[ScheduledRun]:
        async with self._sm() as session:
            rows = (
                await session.execute(
                    select(ScheduledRunModel)
                    .where(ScheduledRunModel.started_at >= when)
                    .order_by(ScheduledRunModel.started_at)
                )
            ).scalars()
            return [_to_domain(r) for r in rows]

    async def close_interrupted(self, *, reason: str, finished_at: datetime) -> int:
        """Rows a stopped daemon left ``running``: none of them is any more."""
        async with self._sm() as session:
            result = await session.execute(
                update(ScheduledRunModel)
                .where(ScheduledRunModel.outcome == "running")
                .values(outcome="failed", reason=reason, finished_at=finished_at)
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def delete_for_channel(self, channel_uid: str) -> None:
        async with self._sm() as session:
            await session.execute(
                delete(ScheduledRunModel).where(ScheduledRunModel.channel_uid == channel_uid)
            )
            await session.commit()
