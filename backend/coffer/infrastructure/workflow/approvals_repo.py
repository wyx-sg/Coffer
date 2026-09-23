"""The ``workflow_approvals`` repository.

Split out of ``repository.py`` for the 400-line file budget, and imported back
into it so a caller still reaches all four repositories from one module.

Everything here turns on one rule: a decision is taken once. Each write is
therefore an UPDATE whose WHERE clause carries the state it expects to find —
``status = 'pending'`` — so a second decision, an expiry racing a click, and
an abort racing an approval all lose the race in the database rather than in a
caller's if-statement (spec workflow "Make an approval decision idempotent").
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.workflow.run import ApprovalStatus
from coffer.infrastructure.workflow.models import WorkflowApprovalModel


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC)


class WorkflowApprovalRepo:
    """Held decisions: created pending, decided once, then terminal forever."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def create_approval(
        self,
        *,
        approval_id: str,
        run_id: str,
        kind: str,
        payload: dict[str, Any],
        expires_at: datetime,
        attempt_id: str | None = None,
        tool_name: str | None = None,
        now: datetime | None = None,
    ) -> WorkflowApprovalModel:
        """Hold a decision, carrying the exact payload that will execute (spec
        workflow "Refuse an unapproved write-class tool call made for a run")."""
        row = WorkflowApprovalModel(
            id=approval_id,
            run_id=run_id,
            attempt_id=attempt_id,
            kind=kind,
            tool_name=tool_name,
            payload=payload,
            status=ApprovalStatus.PENDING.value,
            expires_at=expires_at,
            created_at=_now(now),
        )
        async with self._sm() as session:
            session.add(row)
            await session.commit()
        return row

    async def get_approval(self, approval_id: str) -> WorkflowApprovalModel | None:
        async with self._sm() as session:
            stmt = select(WorkflowApprovalModel).where(WorkflowApprovalModel.id == approval_id)
            row: WorkflowApprovalModel | None = (await session.execute(stmt)).scalar_one_or_none()
            return row

    async def decide_approval(
        self,
        approval_id: str,
        *,
        status: str,
        decided_by: str | None = None,
        decided_surface: str | None = None,
        comment: str | None = None,
        now: datetime | None = None,
    ) -> WorkflowApprovalModel | None:
        """Decide a pending approval, or hand back the terminal state it already has.

        Idempotent by construction (spec workflow "Make an approval decision
        idempotent"): the UPDATE only matches a row still ``pending``, and the
        row is read back either way — so a repeated approval returns
        ``approved`` without a second execution being authorised, and an
        approval that expired a second before the click returns ``expired``
        rather than quietly overwriting it.

        ``None`` means no such approval, which is the one case a caller must
        distinguish from "already decided".
        """
        stamp = _now(now)
        stmt = (
            update(WorkflowApprovalModel)
            .where(
                WorkflowApprovalModel.id == approval_id,
                WorkflowApprovalModel.status == ApprovalStatus.PENDING.value,
            )
            .values(
                status=status,
                decided_by=decided_by,
                decided_surface=decided_surface,
                comment=comment,
                decided_at=stamp,
            )
        )
        async with self._sm() as session:
            await session.execute(stmt)
            await session.commit()
            read = select(WorkflowApprovalModel).where(WorkflowApprovalModel.id == approval_id)
            row: WorkflowApprovalModel | None = (await session.execute(read)).scalar_one_or_none()
            return row

    async def list_approvals(
        self,
        run_id: str,
        *,
        status: str | None = None,
    ) -> list[WorkflowApprovalModel]:
        """A run's approvals, oldest first — the order they were asked in."""
        async with self._sm() as session:
            stmt = select(WorkflowApprovalModel).where(WorkflowApprovalModel.run_id == run_id)
            if status is not None:
                stmt = stmt.where(WorkflowApprovalModel.status == status)
            stmt = stmt.order_by(WorkflowApprovalModel.created_at, WorkflowApprovalModel.id)
            return list((await session.execute(stmt)).scalars().all())

    async def expire_due_approvals(
        self,
        *,
        now: datetime | None = None,
    ) -> list[WorkflowApprovalModel]:
        """Move every pending approval past its deadline to ``expired``.

        Returns the rows it moved, because a held tool call must fail with an
        explicit reason rather than be silently dropped (spec workflow
        "Resume or fail a held tool call, never drop it") — and the thing
        that tells its caller so is this list.
        """
        stamp = _now(now)
        return await self._transition(
            stamp,
            ApprovalStatus.EXPIRED.value,
            WorkflowApprovalModel.expires_at <= stamp,
        )

    async def supersede_pending(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> list[WorkflowApprovalModel]:
        """Retire a run's pending approvals when the run is aborted.

        ``superseded`` rather than ``rejected``: nobody decided these, the
        question simply stopped being asked, and a surface that renders a
        rejection as "the developer said no" would be reporting something that
        did not happen.
        """
        stamp = _now(now)
        return await self._transition(
            stamp,
            ApprovalStatus.SUPERSEDED.value,
            WorkflowApprovalModel.run_id == run_id,
        )

    async def _transition(
        self,
        stamp: datetime,
        to_status: str,
        condition: Any,
    ) -> list[WorkflowApprovalModel]:
        """Move the pending rows matching ``condition`` to a terminal status.

        The ids are collected first and the UPDATE re-states ``pending`` in its
        own WHERE, so an approval decided between the two statements keeps the
        decision a person made; the rows are then read back by id, and only
        those that actually carry the new status are returned.
        """
        async with self._sm() as session:
            ids = list(
                (
                    await session.execute(
                        select(WorkflowApprovalModel.id).where(
                            WorkflowApprovalModel.status == ApprovalStatus.PENDING.value,
                            condition,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if not ids:
                return []
            await session.execute(
                update(WorkflowApprovalModel)
                .where(
                    WorkflowApprovalModel.id.in_(ids),
                    WorkflowApprovalModel.status == ApprovalStatus.PENDING.value,
                )
                .values(status=to_status, decided_at=stamp)
            )
            await session.commit()
            rows = list(
                (
                    await session.execute(
                        select(WorkflowApprovalModel).where(
                            WorkflowApprovalModel.id.in_(ids),
                            WorkflowApprovalModel.status == to_status,
                        )
                    )
                )
                .scalars()
                .all()
            )
            return rows
