"""The gate: whether a run's upstream tool call happens at all (spec
workflow "Refuse an unapproved write-class tool call made for a run").

Coffer does not gate tool calls. That position stands for every conversation a
person is driving (``docs/decisions/remove-tool-approval.md``) and this module
does not touch them — it is reached only for a session that reported a run
identity, and a session that reported none never gets here.

What it answers is narrow: **this call, on behalf of this run, right now.**
Given a prefixed tool name and its arguments it says ALLOW (``None`` — dispatch
it), or it holds the call until a decision arrives and then either allows it or
REFUSES with a reason the agent can read. Nothing in here knows what the
gateway is; the gateway asks through a Protocol, because the import fence runs
both ways (see ``application/mcp/gateway_gate.py``).

Two shapes are worth naming:

* **A refusal is a result, not an exception.** It comes back as a ``tools/call``
  result with ``isError`` set and text saying why. An agent reads that and can
  act on it — "not this region" tells it what to do next — where a JSON-RPC
  error reads as "the gateway broke" and invites a retry against a system that
  is not broken.
* **Waiting is polling the row.** A decision can arrive from HTTP, from the
  CLI, from a channel callback, or from an expiry sweep, and the approval row
  is the one place all four converge. An in-memory signal would be faster and
  would miss the paths that do not go through this process's service object; a
  second's latency is nothing next to a person deciding.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX
from coffer.application.workflow.approval_service import ApprovalService, split_prefixed_tool
from coffer.application.workflow.ports import ApprovalRow, AuditPort, ToolClassPort
from coffer.domain.audit import AuditEventType
from coffer.domain.workflow.run import Approval, ApprovalKind, ApprovalStatus

#: How long a held tool-call approval stands before it authorises nothing.
#: One hour: a run is unattended by definition, so the developer is being
#: pinged on a channel and may be away from the desk — but a decision made
#: tomorrow is a decision about a call whose run has long since moved on, and
#: acting on it then would be worse than asking again.
APPROVAL_TTL_SECONDS = 3600

#: How long the GATEWAY holds the JSON-RPC response open. Deliberately shorter
#: than the approval's life: fifteen minutes is past every downstream client's
#: own tool-call timeout, so holding longer buys nothing but a socket and an
#: agent stuck on a turn. When it elapses the call fails with a reason and the
#: approval stays ``pending`` — the developer's later decision is still
#: recorded, and the node can retry against it rather than losing the answer.
HELD_CALL_MAX_WAIT_SECONDS = 900

#: How often the held call re-reads its approval row. See the module docstring
#: for why it polls at all.
POLL_INTERVAL_SECONDS = 1.0

#: The judgement that lets a call past without asking. Anything else — a
#: ``write``, or nothing recorded at all — is held (spec workflow "Treat
#: an unjudged tool as write-class and remember the answer").
READ_CLASS = "read"

#: Every refusal opens with this, so an agent, a log reader and a diagnosis
#: script can all tell a gated call apart from an upstream that is down. The
#: ADR asks for exactly that distinction.
REFUSAL_PREFIX = "Coffer workflow gate:"


class WorkflowToolGate:
    """Holds a run's write-class upstream calls until the developer decides."""

    def __init__(
        self,
        *,
        approvals: ApprovalService,
        tool_class: ToolClassPort,
        audit: AuditPort,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        max_wait_seconds: float = HELD_CALL_MAX_WAIT_SECONDS,
        ttl_seconds: int = APPROVAL_TTL_SECONDS,
    ) -> None:
        self._approvals = approvals
        self._tool_class = tool_class
        self._audit = audit
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._sleep = sleep or asyncio.sleep
        self._max_wait = max_wait_seconds
        self._ttl = ttl_seconds

    async def check_tool_call(
        self,
        *,
        run_context: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        """``None`` to dispatch; a ``tools/call`` result to return instead."""
        if tool_name.startswith(COFFER_TOOL_PREFIX):
            # A built-in reaches the developer's own vault on their own
            # machine. There is no outside world behind it to protect.
            return None
        split = split_prefixed_tool(tool_name)
        if split is None:
            # Not a namespaced upstream tool, so there is no server to ask
            # about it. The gateway refuses it a moment later on its own terms;
            # holding it here would ask the developer about a call that was
            # never going to happen.
            return None
        run_id, attempt_id = _split_run_context(run_context)
        if not run_id:
            return None
        server, tool = split
        if await self._tool_class.classify(server, tool) == READ_CLASS:
            # Judged a read. Not audited: a run's reads are its ordinary work,
            # and an audit row per tool call would bury the decisions this log
            # exists to hold (spec workflow "Audit template, run, approval and
            # gate events" is about gated calls, not about all of them).
            return None
        return await self._hold(
            run_id=run_id,
            attempt_id=attempt_id,
            tool_name=tool_name,
            arguments=arguments,
        )

    async def _hold(
        self,
        *,
        run_id: str,
        attempt_id: str | None,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        approval = await self._approvals.create(
            run_id=run_id,
            kind=ApprovalKind.TOOL_CALL,
            payload=arguments,
            ttl_seconds=self._ttl,
            attempt_id=attempt_id,
            tool_name=tool_name,
        )
        deadline = self._clock() + timedelta(seconds=self._max_wait)
        row = await self._wait_for_decision(approval.id, deadline=deadline)
        outcome, refusal = self._read_outcome(approval.id, row)
        await self._audit_gated(
            run_id=run_id, tool_name=tool_name, approval_id=approval.id, outcome=outcome
        )
        return refusal

    async def _wait_for_decision(
        self, approval_id: str, *, deadline: datetime
    ) -> ApprovalRow | None:
        """Watch the row until it is answered, overdue, or we stop waiting.

        ``None`` means no decision arrived. Expiry is handled here rather than
        left to a background sweep: the held call is the one thing that cares,
        it is already awake, and a call that outlives its approval must fail
        for a stated reason rather than wait for a sweeper to notice.
        """
        while True:
            row = await self._approvals.get(approval_id)
            if row is None:
                # The run was deleted out from under the call. Nothing left to
                # decide and nothing left to execute for.
                return None
            if row.status != ApprovalStatus.PENDING.value:
                return row
            now = self._clock()
            if _aware(row.expires_at) <= now:
                for expired in await self._approvals.expire_due(now=now):
                    if expired.id == approval_id:
                        return expired
                return await self._approvals.get(approval_id)
            if now >= deadline:
                return None
            await self._sleep(POLL_INTERVAL_SECONDS)

    def _read_outcome(
        self, approval_id: str, row: ApprovalRow | None
    ) -> tuple[str, dict[str, Any] | None]:
        """Turn the decided row into (audit outcome, refusal-or-None)."""
        if row is None:
            return "timed_out", _refusal(
                f"no decision on approval {approval_id} within "
                f"{int(self._max_wait)}s. It is still pending — the developer can "
                "decide it and the node can try again."
            )
        approval = _approval_from_row(row)
        if approval.authorises_at(self._clock()):
            return "approved", None
        if approval.status is ApprovalStatus.REJECTED:
            because = f" Reason: {approval.comment}" if approval.comment else ""
            return "rejected", _refusal(f"the developer rejected approval {approval_id}.{because}")
        if approval.status is ApprovalStatus.SUPERSEDED:
            return "superseded", _refusal(
                f"approval {approval_id} was retired because its run was aborted."
            )
        # Either the sweep moved it to ``expired``, or it is still marked
        # ``approved`` but its deadline passed while the call was in flight.
        # ``Approval.authorises_at`` refuses both, and so does the wording.
        return "expired", _refusal(
            f"approval {approval_id} expired before the call could be made. "
            "Nothing was sent upstream."
        )

    async def _audit_gated(
        self, *, run_id: str, tool_name: str, approval_id: str, outcome: str
    ) -> None:
        await self._audit.record(
            AuditEventType.WORKFLOW_TOOL_CALL_GATED.value,
            actor="workflow",
            subject_kind="workflow_run",
            subject_name=run_id,
            detail={"tool_name": tool_name, "approval_id": approval_id, "outcome": outcome},
        )


def _refusal(reason: str) -> dict[str, Any]:
    """A ``tools/call`` result the agent reads as a stated refusal."""
    return {
        "content": [{"type": "text", "text": f"{REFUSAL_PREFIX} {reason}"}],
        "isError": True,
    }


def _split_run_context(run_context: str) -> tuple[str, str | None]:
    """``"run_01J/att_07"`` -> ``("run_01J", "att_07")``.

    The attempt half is optional: a run identity with no attempt still
    attributes the call to the run, which is what the gate needs. Parsing lives
    on this side because the gateway carries the string opaquely.
    """
    run_id, separator, attempt_id = run_context.partition("/")
    return run_id.strip(), (attempt_id.strip() or None) if separator else None


def _aware(value: datetime) -> datetime:
    """UTC-anchor a timestamp SQLite may have handed back without a zone.

    Comparing a naive datetime to an aware one raises, and the comparison this
    guards decides whether a write happens — so it fails closed by assuming the
    stored value is the UTC the repository wrote, never by skipping the check.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _approval_from_row(row: ApprovalRow) -> Approval:
    """The domain entity behind the repository's row.

    Worth the few lines: ``Approval.authorises_at`` is where "approved" and
    "still valid" are decided together, and reimplementing that comparison at
    the call site is how the two answers drift apart.
    """
    return Approval(
        id=row.id,
        run_id=row.run_id,
        kind=ApprovalKind(row.kind),
        payload=row.payload,
        expires_at=_aware(row.expires_at),
        status=ApprovalStatus(row.status),
        attempt_id=row.attempt_id,
        tool_name=row.tool_name,
        decided_by=row.decided_by,
        decided_surface=row.decided_surface,
        comment=row.comment,
    )
