"""ApprovalService: created once, decided once, expired on a clock (FR-033/036/038/039/040).

The repository is faked in memory with the same rule the real one enforces in
SQL — a decision only lands on a row that is still ``pending`` — because that
rule is what every test here is really about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from coffer.application.workflow.approval_service import ApprovalService, split_prefixed_tool
from coffer.domain.audit import AuditEventType
from coffer.domain.workflow.events import EventType
from coffer.domain.workflow.run import ApprovalKind, ApprovalStatus

START = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)

#: A payload with nesting, unicode and an empty container — anything that
#: "summarises" a payload mangles at least one of these.
VERBATIM: dict[str, Any] = {
    "project": "COF",
    "fields": {"labels": ["urgent", "运维"], "watchers": []},
    "body": "line one\nline two",
}


@dataclass
class FakeRow:
    id: str
    run_id: str
    kind: str
    payload: dict[str, Any]
    expires_at: datetime
    status: str = ApprovalStatus.PENDING.value
    attempt_id: str | None = None
    tool_name: str | None = None
    decided_by: str | None = None
    decided_surface: str | None = None
    comment: str | None = None
    created_at: datetime = START
    decided_at: datetime | None = None


class FakeApprovalRepo:
    def __init__(self) -> None:
        self.rows: dict[str, FakeRow] = {}

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
    ) -> FakeRow:
        row = FakeRow(
            id=approval_id,
            run_id=run_id,
            kind=kind,
            payload=payload,
            expires_at=expires_at,
            attempt_id=attempt_id,
            tool_name=tool_name,
            created_at=now or START,
        )
        self.rows[approval_id] = row
        return row

    async def get_approval(self, approval_id: str) -> FakeRow | None:
        return self.rows.get(approval_id)

    async def decide_approval(
        self,
        approval_id: str,
        *,
        status: str,
        decided_by: str | None = None,
        decided_surface: str | None = None,
        comment: str | None = None,
        now: datetime | None = None,
    ) -> FakeRow | None:
        row = self.rows.get(approval_id)
        if row is None:
            return None
        # The real repository's UPDATE ... WHERE status = 'pending'.
        if row.status == ApprovalStatus.PENDING.value:
            row.status = status
            row.decided_by = decided_by
            row.decided_surface = decided_surface
            row.comment = comment
            row.decided_at = now
        return row

    async def list_approvals(self, run_id: str, *, status: str | None = None) -> list[FakeRow]:
        return [
            r
            for r in self.rows.values()
            if r.run_id == run_id and (status is None or r.status == status)
        ]

    async def expire_due_approvals(self, *, now: datetime | None = None) -> list[FakeRow]:
        stamp = now or START
        moved = []
        for row in self.rows.values():
            if row.status == ApprovalStatus.PENDING.value and row.expires_at <= stamp:
                row.status = ApprovalStatus.EXPIRED.value
                row.decided_at = stamp
                moved.append(row)
        return moved

    async def supersede_pending(self, run_id: str, *, now: datetime | None = None) -> list[FakeRow]:
        return []


@dataclass
class FakeEvents:
    appended: list[dict[str, Any]] = field(default_factory=list)

    async def append_event(self, **kwargs: Any) -> Any:
        self.appended.append(kwargs)
        return None

    async def list_events(self, run_id: str, **kwargs: Any) -> list[Any]:
        return []

    @property
    def types(self) -> list[str]:
        return [e["event_type"] for e in self.appended]


@dataclass
class FakeAudit:
    records: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def record(self, event_type: str, **kwargs: Any) -> None:
        self.records.append((event_type, kwargs))


@dataclass
class FakeNotify:
    asked: list[tuple[str, str, str]] = field(default_factory=list)
    announced: list[tuple[str, str]] = field(default_factory=list)

    async def announce(self, run_id: str, text: str) -> None:
        self.announced.append((run_id, text))

    async def request_approval(self, run_id: str, approval_id: str, preview: str) -> None:
        self.asked.append((run_id, approval_id, preview))


@dataclass
class FakeToolClass:
    known: dict[tuple[str, str], str] = field(default_factory=dict)
    remembered: list[tuple[str, str, str]] = field(default_factory=list)

    async def classify(self, server_name: str, tool: str) -> str | None:
        return self.known.get((server_name, tool))

    async def remember(self, server_name: str, tool: str, write_class: str) -> None:
        self.remembered.append((server_name, tool, write_class))
        self.known[(server_name, tool)] = write_class


@dataclass
class Harness:
    service: ApprovalService
    repo: FakeApprovalRepo
    events: FakeEvents
    audit: FakeAudit
    notify: FakeNotify
    tool_class: FakeToolClass


def build() -> Harness:
    repo, events, audit = FakeApprovalRepo(), FakeEvents(), FakeAudit()
    notify, tool_class = FakeNotify(), FakeToolClass()
    counter = iter(f"id{n}" for n in range(1, 1000))
    service = ApprovalService(
        approvals=repo,
        events=events,
        audit=audit,
        notify=notify,
        tool_class=tool_class,
        clock=lambda: START,
        new_id=lambda: next(counter),
    )
    return Harness(service, repo, events, audit, notify, tool_class)


async def _held(h: Harness, **overrides: Any) -> FakeRow:
    kwargs: dict[str, Any] = {
        "run_id": "run1",
        "kind": ApprovalKind.TOOL_CALL,
        "payload": VERBATIM,
        "ttl_seconds": 600,
        "attempt_id": "att1",
        "tool_name": "jira__create_issue",
    }
    kwargs.update(overrides)
    return await h.service.create(**kwargs)


# --- create -----------------------------------------------------------------


async def test_the_payload_is_the_arguments_verbatim() -> None:
    """FR-033: a decision on a summary is not a decision."""
    h = build()
    row = await _held(h)
    assert row.payload == VERBATIM
    assert row.payload["fields"]["labels"] == ["urgent", "运维"]
    assert row.payload["body"] == "line one\nline two"


@pytest.mark.acceptance(
    spec="workflow", scenario="an approval reaches the developer where they are"
)
async def test_creating_an_approval_reaches_the_developer() -> None:
    """FR-039: the main thread and any bound channel, both behind NotifyPort."""
    h = build()
    row = await _held(h)
    assert h.notify.asked == [("run1", row.id, h.notify.asked[0][2])]
    assert "jira__create_issue" in h.notify.asked[0][2]
    assert EventType.APPROVAL_CREATED.value in h.events.types


async def test_expiry_is_the_ttl_from_now() -> None:
    h = build()
    row = await _held(h, ttl_seconds=90)
    assert row.expires_at == START + timedelta(seconds=90)


# --- decide -----------------------------------------------------------------


async def test_a_decision_is_evented_and_audited() -> None:
    """FR-040: every approval decision is audited."""
    h = build()
    row = await _held(h)
    decided = await h.service.decide(
        row.id,
        decision=ApprovalStatus.APPROVED,
        decided_by="yuxing",
        decided_surface="web",
        comment="ok",
    )
    assert decided is not None and decided.status == ApprovalStatus.APPROVED.value
    assert EventType.APPROVAL_APPROVED.value in h.events.types
    assert [t for t, _ in h.audit.records] == [AuditEventType.WORKFLOW_APPROVAL_DECIDED.value]
    assert h.audit.records[0][1]["detail"]["approval_id"] == row.id


@pytest.mark.acceptance(spec="workflow", scenario="an approval decision is idempotent")
async def test_a_repeated_decision_changes_nothing_and_records_nothing() -> None:
    """FR-038: the same terminal state comes back and nothing happens twice."""
    h = build()
    row = await _held(h)
    first = await h.service.decide(row.id, decision=ApprovalStatus.APPROVED, decided_by="yuxing")
    again = await h.service.decide(row.id, decision=ApprovalStatus.APPROVED, decided_by="yuxing")
    assert first is not None and again is not None
    assert again.status == first.status == ApprovalStatus.APPROVED.value
    assert again.decided_by == "yuxing"
    assert len(h.audit.records) == 1
    assert h.events.types.count(EventType.APPROVAL_APPROVED.value) == 1


@pytest.mark.acceptance(spec="workflow", scenario="an approval decision is idempotent")
async def test_a_contradicting_second_decision_loses() -> None:
    h = build()
    row = await _held(h)
    await h.service.decide(row.id, decision=ApprovalStatus.APPROVED)
    flipped = await h.service.decide(row.id, decision=ApprovalStatus.REJECTED)
    assert flipped is not None and flipped.status == ApprovalStatus.APPROVED.value
    assert EventType.APPROVAL_REJECTED.value not in h.events.types


async def test_deciding_an_expired_approval_returns_expired() -> None:
    h = build()
    row = await _held(h, ttl_seconds=1)
    await h.service.expire_due(now=START + timedelta(seconds=2))
    h.audit.records.clear()
    decided = await h.service.decide(row.id, decision=ApprovalStatus.APPROVED)
    assert decided is not None and decided.status == ApprovalStatus.EXPIRED.value
    assert h.audit.records == []


async def test_deciding_an_unknown_approval_is_none_not_a_new_row() -> None:
    h = build()
    assert await h.service.decide("nope", decision=ApprovalStatus.APPROVED) is None
    assert h.repo.rows == {}


@pytest.mark.parametrize(
    "status", [ApprovalStatus.EXPIRED, ApprovalStatus.SUPERSEDED, ApprovalStatus.PENDING]
)
async def test_only_a_person_s_two_answers_are_decisions(status: ApprovalStatus) -> None:
    h = build()
    row = await _held(h)
    with pytest.raises(ValueError):
        await h.service.decide(row.id, decision=status)


# --- remembering the judgement ----------------------------------------------


@pytest.mark.acceptance(spec="workflow", scenario="an unknown tool is treated as write-class")
async def test_the_answer_is_remembered_on_the_server() -> None:
    """FR-036: the same tool is not asked about twice."""
    h = build()
    row = await _held(h)
    await h.service.decide(row.id, decision=ApprovalStatus.APPROVED, remember_tool_class="write")
    assert h.tool_class.remembered == [("jira", "create_issue", "write")]


async def test_nothing_is_remembered_when_the_developer_did_not_say() -> None:
    h = build()
    row = await _held(h)
    await h.service.decide(row.id, decision=ApprovalStatus.APPROVED)
    assert h.tool_class.remembered == []


async def test_an_unprefixed_tool_name_records_no_judgement() -> None:
    h = build()
    row = await _held(h, tool_name="create_issue")
    await h.service.decide(row.id, decision=ApprovalStatus.APPROVED, remember_tool_class="write")
    assert h.tool_class.remembered == []


# --- expire -----------------------------------------------------------------


async def test_expiry_moves_only_overdue_rows_and_audits_them() -> None:
    h = build()
    soon = await _held(h, ttl_seconds=1)
    later = await _held(h, ttl_seconds=10_000)
    moved = await h.service.expire_due(now=START + timedelta(seconds=5))
    assert [r.id for r in moved] == [soon.id]
    assert later.status == ApprovalStatus.PENDING.value
    assert [t for t, _ in h.audit.records] == [AuditEventType.WORKFLOW_APPROVAL_DECIDED.value]
    assert EventType.APPROVAL_EXPIRED.value in h.events.types


async def test_listing_narrows_by_status() -> None:
    h = build()
    row = await _held(h)
    await h.service.decide(row.id, decision=ApprovalStatus.REJECTED)
    await _held(h)
    pending = await h.service.list_for_run("run1", status=ApprovalStatus.PENDING)
    assert [r.id for r in pending] != [row.id]
    assert len(await h.service.list_for_run("run1")) == 2


# --- the namespace split ----------------------------------------------------


@pytest.mark.parametrize(
    ("prefixed", "expected"),
    [
        ("jira__create_issue", ("jira", "create_issue")),
        ("gitlab__merge_requests__create", ("gitlab", "merge_requests__create")),
        ("create_issue", None),
        ("__create_issue", None),
        ("jira__", None),
        ("", None),
    ],
)
def test_the_first_double_underscore_is_the_separator(
    prefixed: str, expected: tuple[str, str] | None
) -> None:
    assert split_prefixed_tool(prefixed) == expected
