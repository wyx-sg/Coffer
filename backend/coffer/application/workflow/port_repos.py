"""The four repositories, described structurally (spec workflow).

Split out of :mod:`ports` on the same seam ``port_rows`` was, and for the same
file-size reason: this module is the run's own PERSISTENCE — four tables one
kind owns — while ``ports`` is the set of seams out to other kinds. They are
re-exported from ``ports`` so callers keep one import.

Application code may not import the ORM, so a repository satisfies these by
having the methods, not by inheriting anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from coffer.application.workflow.port_rows import (
    ApprovalRow,
    AttemptRow,
    EventRow,
    RunRow,
)
from coffer.domain.workflow.run import RunProjection

__all__ = [
    "ApprovalRepoPort",
    "AttemptRepoPort",
    "EventRepoPort",
    "RunRepoPort",
]


class RunRepoPort(Protocol):
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
    ) -> RunRow: ...

    async def get_run(self, run_id: str) -> RunRow | None: ...

    async def list_runs(
        self, *, status: str | None = None, limit: int | None = None
    ) -> Sequence[RunRow]: ...

    async def update_run_projection(
        self,
        run_id: str,
        expected_version: int,
        projection: RunProjection,
        *,
        now: datetime | None = None,
    ) -> RunRow | None:
        """Write the projection, or return ``None`` when the version moved.

        A conflict is a return value rather than an exception because the
        caller always has something to say about it — the current run comes
        back on the next read and the refusal carries it (FR-015)."""
        ...

    async def set_inputs(
        self,
        run_id: str,
        inputs: list[Any],
        *,
        now: datetime | None = None,
    ) -> RunRow | None:
        """Replace the run's mounted inputs; ``None`` when the run is gone.

        Outside the version cycle (FR-050): mounting a PRD advances nothing, so
        bumping the version would invalidate every open client's observed
        version for a change that moves the run nowhere."""
        ...

    async def set_label(
        self,
        run_id: str,
        *,
        title: str,
        description: str | None,
        now: datetime | None = None,
    ) -> RunRow | None:
        """Rewrite the run's title and description; ``None`` when it is gone.

        Outside the version cycle for the same reason ``set_inputs`` is
        (FR-070): a label is not the projection. The status, the stage and the
        position are folded from the events and only the engine writes them;
        what the developer called the work is theirs to correct, and bumping
        the version for it would invalidate every open client's observed
        version for a change that moves the run nowhere."""
        ...

    async def delete_run(self, run_id: str) -> None: ...


class EventRepoPort(Protocol):
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
    ) -> EventRow: ...

    async def list_events(
        self, run_id: str, *, after_sequence: int | None = None, limit: int | None = None
    ) -> Sequence[EventRow]: ...


class AttemptRepoPort(Protocol):
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
    ) -> AttemptRow: ...

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
    ) -> AttemptRow | None:
        """``None`` for a field means leave it alone, not set it null."""
        ...

    async def latest_attempt(self, run_id: str, node_key: str) -> AttemptRow | None: ...

    async def attempt_by_conversation(self, conversation_id: str) -> AttemptRow | None:
        """The attempt whose work happens in this conversation, or ``None``.

        Derivable from persistence rather than from an in-process map, so a
        turn started after a daemon restart still carries its run identity and
        is still gated."""
        ...

    async def list_attempts(self, run_id: str) -> Sequence[AttemptRow]: ...


class ApprovalRepoPort(Protocol):
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
    ) -> ApprovalRow: ...

    async def get_approval(self, approval_id: str) -> ApprovalRow | None: ...

    async def decide_approval(
        self,
        approval_id: str,
        *,
        status: str,
        decided_by: str | None = None,
        decided_surface: str | None = None,
        comment: str | None = None,
        now: datetime | None = None,
    ) -> ApprovalRow | None: ...

    async def list_approvals(
        self, run_id: str, *, status: str | None = None
    ) -> Sequence[ApprovalRow]: ...

    async def expire_due_approvals(
        self, *, now: datetime | None = None
    ) -> Sequence[ApprovalRow]: ...

    async def supersede_pending(
        self, run_id: str, *, now: datetime | None = None
    ) -> Sequence[ApprovalRow]: ...
