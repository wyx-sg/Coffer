"""Approvals: created once, decided once, expired on a clock (spec workflow).

An approval is the only thing standing between a prepared external write and
its execution, so this service is written around one property: **a decision
happens once**. The repository enforces that in SQL — every write is an UPDATE
whose WHERE clause re-states ``status = 'pending'`` — and this layer never
tries to enforce it a second time in Python. What it adds is everything a
decision owes the rest of the system: the run's event log, the audit trail
(FR-040), the developer's notification (FR-039), and the remembered
write-class judgement (FR-036).

The service does **not** execute anything. A held tool call is waiting in
:mod:`coffer.application.workflow.gate`, watching the row this service writes;
keeping the execution out of here is what makes "a repeated decision executes
nothing twice" (FR-038) structural rather than careful.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from coffer.application.workflow.ports import (
    ApprovalRepoPort,
    ApprovalRow,
    AuditPort,
    EventRepoPort,
    NotifyPort,
    ToolClassPort,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.workflow.events import ActorKind, EventType
from coffer.domain.workflow.run import ApprovalKind, ApprovalStatus

#: The decisions a person is allowed to make. ``expired`` and ``superseded``
#: are outcomes the system reaches on its own and are not accepted here — a
#: surface that could post them could forge one.
DECIDABLE: frozenset[ApprovalStatus] = frozenset({ApprovalStatus.APPROVED, ApprovalStatus.REJECTED})

#: How much of a payload goes into the notification. The approval row keeps the
#: arguments verbatim (FR-033); this is the glance that gets the developer to
#: open it, and a channel message is not the place to paste an unbounded blob.
_PREVIEW_CHARS = 400

_EVENT_FOR_STATUS: dict[ApprovalStatus, EventType] = {
    ApprovalStatus.APPROVED: EventType.APPROVAL_APPROVED,
    ApprovalStatus.REJECTED: EventType.APPROVAL_REJECTED,
    ApprovalStatus.EXPIRED: EventType.APPROVAL_EXPIRED,
}


def split_prefixed_tool(prefixed: str) -> tuple[str, str] | None:
    """``"jira__create_issue"`` -> ``("jira", "create_issue")``; ``None`` if unprefixed.

    Lives here rather than being imported from the MCP layer because the import
    fence forbids that direction, and because the rule is one line: a server
    name may not contain ``__``, so the first occurrence is the separator.
    """
    server, separator, tool = prefixed.partition("__")
    if not separator or not server or not tool:
        return None
    return server, tool


class ApprovalService:
    """Create, decide, expire and list a run's approvals."""

    def __init__(
        self,
        *,
        approvals: ApprovalRepoPort,
        events: EventRepoPort,
        audit: AuditPort,
        notify: NotifyPort,
        tool_class: ToolClassPort,
        clock: Callable[[], datetime] | None = None,
        new_id: Callable[[], str] | None = None,
    ) -> None:
        self._approvals = approvals
        self._events = events
        self._audit = audit
        self._notify = notify
        self._tool_class = tool_class
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._new_id = new_id or (lambda: uuid.uuid4().hex)

    # --- create ---------------------------------------------------------

    async def create(
        self,
        *,
        run_id: str,
        kind: ApprovalKind,
        payload: dict[str, Any],
        ttl_seconds: int,
        attempt_id: str | None = None,
        tool_name: str | None = None,
    ) -> ApprovalRow:
        """Hold a decision and put it in front of the developer.

        ``payload`` is stored exactly as given — the arguments that will
        execute, not a rendering of them. A decision on a summary is not a
        decision (FR-033), so nothing between here and the database is allowed
        to shorten it; the shortening happens only in the notification.
        """
        now = self._clock()
        row = await self._approvals.create_approval(
            approval_id=self._new_id(),
            run_id=run_id,
            kind=kind.value,
            payload=payload,
            expires_at=now + timedelta(seconds=ttl_seconds),
            attempt_id=attempt_id,
            tool_name=tool_name,
            now=now,
        )
        await self._append_event(
            row,
            EventType.APPROVAL_CREATED,
            ActorKind.WORKFLOW,
            source_surface="workflow",
        )
        # FR-039: the main thread always carries it; a bound channel also
        # delivers it. Both are behind NotifyPort, which is allowed to do
        # nothing — a vault with no channel is not a broken vault.
        await self._notify.request_approval(run_id, row.id, _preview(row))
        return row

    async def get(self, approval_id: str) -> ApprovalRow | None:
        return await self._approvals.get_approval(approval_id)

    async def list_for_run(
        self, run_id: str, *, status: ApprovalStatus | None = None
    ) -> Sequence[ApprovalRow]:
        return await self._approvals.list_approvals(
            run_id, status=None if status is None else status.value
        )

    # --- decide ---------------------------------------------------------

    async def decide(
        self,
        approval_id: str,
        *,
        decision: ApprovalStatus,
        decided_by: str | None = None,
        decided_surface: str | None = None,
        comment: str | None = None,
        remember_tool_class: str | None = None,
    ) -> ApprovalRow | None:
        """Decide once; a repeat returns the same terminal state (FR-038).

        ``None`` means there is no such approval — the one case a caller must
        tell apart from "already decided". Otherwise the row comes back in
        whatever terminal state it holds, which may not be the decision that
        was asked for: an approval that expired a second before the click
        returns ``expired``, and the caller renders that rather than pretending
        the click landed.

        Nothing here executes the approved work. The held call is waiting on
        this row, so a second decision that changes nothing also does nothing.
        """
        if decision not in DECIDABLE:
            raise ValueError(f"{decision!r} is not a decision a person can make")
        existing = await self._approvals.get_approval(approval_id)
        if existing is None:
            return None
        if existing.status != ApprovalStatus.PENDING.value:
            # Already answered. Return it untouched: no second event, no second
            # audit entry, and — because the gate reads the row rather than
            # being called — no second execution.
            return existing
        row = await self._approvals.decide_approval(
            approval_id,
            status=decision.value,
            decided_by=decided_by,
            decided_surface=decided_surface,
            comment=comment,
            now=self._clock(),
        )
        if row is None:
            return None
        if remember_tool_class is not None:
            await self._remember(row, remember_tool_class)
        await self._record(row, ApprovalStatus(row.status), actor=decided_by or "user")
        return row

    # --- expire ---------------------------------------------------------

    async def expire_due(self, *, now: datetime | None = None) -> Sequence[ApprovalRow]:
        """Move every overdue pending approval to ``expired`` and report them.

        The list is the point: a held call must fail with an explicit reason
        rather than be dropped (FR-037), and these rows are what tell the gate
        — and the audit log — that the reason is expiry rather than a refusal.
        """
        rows = await self._approvals.expire_due_approvals(now=now or self._clock())
        for row in rows:
            await self._record(row, ApprovalStatus.EXPIRED, actor="system")
        return rows

    # --- internals ------------------------------------------------------

    async def _remember(self, row: ApprovalRow, write_class: str) -> None:
        """Write the developer's judgement back so the tool is asked about once."""
        if row.tool_name is None:
            return
        split = split_prefixed_tool(row.tool_name)
        if split is None:
            return
        server, tool = split
        await self._tool_class.remember(server, tool, write_class)

    async def _record(self, row: ApprovalRow, status: ApprovalStatus, *, actor: str) -> None:
        event_type = _EVENT_FOR_STATUS.get(status)
        if event_type is not None:
            await self._append_event(
                row,
                event_type,
                ActorKind.USER if status in DECIDABLE else ActorKind.SYSTEM,
                source_surface=row.decided_surface or "workflow",
                actor_id=row.decided_by,
            )
        await self._audit.record(
            AuditEventType.WORKFLOW_APPROVAL_DECIDED.value,
            actor=actor,
            resource_kind="workflow_run",
            resource_name=row.run_id,
            detail={
                "approval_id": row.id,
                "kind": row.kind,
                "tool_name": row.tool_name,
                "status": row.status,
                "comment": row.comment,
            },
        )

    async def _append_event(
        self,
        row: ApprovalRow,
        event_type: EventType,
        actor_kind: ActorKind,
        *,
        source_surface: str,
        actor_id: str | None = None,
    ) -> None:
        # The arguments are deliberately NOT copied into the event payload. The
        # approval row is the one verbatim copy; a second would be a second
        # thing to keep true, and the timeline only needs the reference.
        await self._events.append_event(
            event_id=self._new_id(),
            run_id=row.run_id,
            event_type=event_type.value,
            actor={
                "actor_kind": actor_kind.value,
                "source_surface": source_surface,
                "actor_id": actor_id,
            },
            payload={
                "approval_id": row.id,
                "kind": row.kind,
                "tool_name": row.tool_name,
                "comment": row.comment,
            },
            now=self._clock(),
        )


def _preview(row: ApprovalRow) -> str:
    """One glance at what is being asked, for the channel message."""
    body = json.dumps(row.payload, ensure_ascii=False, default=str, sort_keys=True)
    if len(body) > _PREVIEW_CHARS:
        body = body[:_PREVIEW_CHARS] + "… (truncated; the full arguments are on the approval)"
    subject = row.tool_name or row.kind
    return f"{subject}\n{body}"
