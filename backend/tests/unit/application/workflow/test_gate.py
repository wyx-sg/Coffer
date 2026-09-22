"""The gate's decision, on its own (FR-034/036/037/040).

The gateway is not here: this tier asks the gate the question directly and
checks the four outcomes a held call can have — approved, rejected, expired,
timed out — plus the three calls it must never hold. The gateway's side of the
same seam is ``tests/unit/application/mcp/test_gateway_workflow_gate.py``.

Time is a counter, not a wall clock: the fake ``sleep`` advances it and may run
one scripted action per tick, which is how "the developer approves while the
call is held" happens deterministically and in microseconds.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from coffer.application.workflow.approval_service import ApprovalService
from coffer.application.workflow.gate import REFUSAL_PREFIX, WorkflowToolGate
from coffer.domain.audit import AuditEventType
from coffer.domain.workflow.run import ApprovalStatus

from .test_approval_service import (
    VERBATIM,
    FakeApprovalRepo,
    FakeAudit,
    FakeEvents,
    FakeNotify,
    FakeToolClass,
)

START = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
RUN_CONTEXT = "run1/att1"


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@dataclass
class Harness:
    gate: WorkflowToolGate
    service: ApprovalService
    repo: FakeApprovalRepo
    audit: FakeAudit
    notify: FakeNotify
    tool_class: FakeToolClass
    clock: Clock
    ticks: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    @property
    def gated_audit(self) -> list[dict[str, Any]]:
        return [
            kwargs["detail"]
            for event_type, kwargs in self.audit.records
            if event_type == AuditEventType.WORKFLOW_TOOL_CALL_GATED.value
        ]


def build(
    *,
    known: dict[tuple[str, str], str] | None = None,
    max_wait_seconds: float = 900.0,
    ttl_seconds: int = 3600,
) -> Harness:
    repo, events, audit = FakeApprovalRepo(), FakeEvents(), FakeAudit()
    notify, tool_class = FakeNotify(), FakeToolClass(known=dict(known or {}))
    clock = Clock()
    counter = iter(f"ap{n}" for n in range(1, 1000))
    ticks: list[Callable[[], Awaitable[None]]] = []

    async def sleep(seconds: float) -> None:
        clock.now += timedelta(seconds=seconds)
        if ticks:
            await ticks.pop(0)()

    service = ApprovalService(
        approvals=repo,
        events=events,
        audit=audit,
        notify=notify,
        tool_class=tool_class,
        clock=clock,
        new_id=lambda: next(counter),
    )
    gate = WorkflowToolGate(
        approvals=service,
        tool_class=tool_class,
        audit=audit,
        clock=clock,
        sleep=sleep,
        max_wait_seconds=max_wait_seconds,
        ttl_seconds=ttl_seconds,
    )
    return Harness(gate, service, repo, audit, notify, tool_class, clock, ticks)


def decide_on_tick(
    h: Harness, *, decision: ApprovalStatus, comment: str | None = None
) -> Callable[[], Awaitable[None]]:
    async def action() -> None:
        approval_id = next(iter(h.repo.rows))
        await h.service.decide(approval_id, decision=decision, decided_by="yuxing", comment=comment)

    return action


async def check(h: Harness, tool: str = "jira__create_issue") -> dict[str, Any] | None:
    return await h.gate.check_tool_call(run_context=RUN_CONTEXT, tool_name=tool, arguments=VERBATIM)


def text_of(refusal: dict[str, Any] | None) -> str:
    assert refusal is not None
    assert refusal["isError"] is True
    return str(refusal["content"][0]["text"])


# --- what is never held ------------------------------------------------------


async def test_a_builtin_tool_is_never_gated() -> None:
    """``coffer__*`` reaches the developer's own vault, not the outside world."""
    h = build()
    assert await check(h, "coffer__write") is None
    assert h.repo.rows == {}
    assert h.gated_audit == []


async def test_a_read_class_tool_is_not_held() -> None:
    h = build(known={("jira", "search_issues"): "read"})
    assert await check(h, "jira__search_issues") is None
    assert h.repo.rows == {}


async def test_an_unprefixed_name_is_left_for_the_gateway_to_refuse() -> None:
    """No server to ask about, so asking the developer would be asking about a
    call that was never going to happen."""
    h = build()
    assert await check(h, "create_issue") is None
    assert h.repo.rows == {}


# --- what is held ------------------------------------------------------------


@pytest.mark.acceptance(spec="workflow", scenario="an unknown tool is treated as write-class")
async def test_a_tool_with_no_recorded_judgement_is_held() -> None:
    """FR-036: unknown means write-class."""
    h = build(max_wait_seconds=2.0)
    refusal = await check(h, "jira__never_seen_before")
    assert "no decision" in text_of(refusal)
    assert len(h.repo.rows) == 1


async def test_a_held_approval_carries_the_arguments_verbatim() -> None:
    """FR-033: the developer decides on what will execute, not a rendering."""
    h = build(max_wait_seconds=1.0)
    await check(h)
    row = next(iter(h.repo.rows.values()))
    assert row.payload == VERBATIM
    assert row.tool_name == "jira__create_issue"
    assert row.run_id == "run1"
    assert row.attempt_id == "att1"


# --- the four outcomes -------------------------------------------------------


@pytest.mark.acceptance(spec="workflow", scenario="an approved call goes through exactly once")
async def test_approved_allows_the_call() -> None:
    """FR-037: a held call resumes once approved."""
    h = build(known={("jira", "create_issue"): "write"})
    h.ticks.append(decide_on_tick(h, decision=ApprovalStatus.APPROVED))
    assert await check(h) is None
    assert h.gated_audit == [
        {"tool_name": "jira__create_issue", "approval_id": "ap1", "outcome": "approved"}
    ]


@pytest.mark.acceptance(
    spec="workflow", scenario="a write-class tool call without an approval is refused"
)
async def test_rejected_refuses_with_the_developer_s_reason() -> None:
    h = build(known={("jira", "create_issue"): "write"})
    h.ticks.append(decide_on_tick(h, decision=ApprovalStatus.REJECTED, comment="not this region"))
    refusal = await check(h)
    assert REFUSAL_PREFIX in text_of(refusal)
    assert "rejected" in text_of(refusal)
    assert "not this region" in text_of(refusal)
    assert h.gated_audit[0]["outcome"] == "rejected"


@pytest.mark.acceptance(spec="workflow", scenario="an expired approval does not authorise a write")
async def test_expiry_refuses_and_says_nothing_was_sent() -> None:
    """FR-037: an approval past its expiry authorises nothing."""
    h = build(ttl_seconds=2, max_wait_seconds=600.0)
    refusal = await check(h)
    assert "expired" in text_of(refusal)
    assert "Nothing was sent upstream" in text_of(refusal)
    assert next(iter(h.repo.rows.values())).status == ApprovalStatus.EXPIRED.value
    assert h.gated_audit[0]["outcome"] == "expired"


@pytest.mark.acceptance(spec="workflow", scenario="an expired approval does not authorise a write")
async def test_an_approval_that_expires_before_the_call_authorises_nothing() -> None:
    """Approved, then overdue by the time the gate reads it back."""
    h = build(ttl_seconds=2, max_wait_seconds=600.0)

    async def approve_late() -> None:
        approval_id = next(iter(h.repo.rows))
        # Decide while still pending, but the clock is already past expiry —
        # the row says ``approved`` and ``Approval.authorises_at`` says no.
        row = h.repo.rows[approval_id]
        row.expires_at = h.clock.now
        await h.service.decide(approval_id, decision=ApprovalStatus.APPROVED)

    h.ticks.append(approve_late)
    refusal = await check(h)
    assert "expired" in text_of(refusal)
    assert h.gated_audit[0]["outcome"] == "expired"


async def test_waiting_too_long_fails_with_a_stated_reason_not_a_hang() -> None:
    h = build(max_wait_seconds=5.0)
    refusal = await check(h)
    text = text_of(refusal)
    assert "no decision" in text
    assert "within 5s" in text
    assert "still pending" in text
    # The approval survives: the developer's later answer is not thrown away.
    assert next(iter(h.repo.rows.values())).status == ApprovalStatus.PENDING.value
    assert h.gated_audit[0]["outcome"] == "timed_out"


async def test_a_held_call_never_comes_back_without_a_reason() -> None:
    """Whatever happens, the agent gets either a dispatch or readable text."""
    h = build(max_wait_seconds=3.0)
    refusal = await check(h)
    assert text_of(refusal).startswith(REFUSAL_PREFIX)


# --- audit -------------------------------------------------------------------


async def test_every_held_call_is_audited_exactly_once() -> None:
    """FR-040: every gated tool call is recorded."""
    h = build(max_wait_seconds=1.0)
    await check(h)
    await check(h, "jira__delete_issue")
    assert [d["tool_name"] for d in h.gated_audit] == [
        "jira__create_issue",
        "jira__delete_issue",
    ]
    assert all(d["outcome"] == "timed_out" for d in h.gated_audit)


@pytest.mark.parametrize("tool", ["coffer__search", "jira__search_issues", "bare_name"])
async def test_a_call_that_is_not_held_writes_no_audit_row(tool: str) -> None:
    """A run's reads are its ordinary work; an audit row each would bury the
    decisions the log exists to hold."""
    h = build(known={("jira", "search_issues"): "read"})
    assert await check(h, tool) is None
    assert h.gated_audit == []
