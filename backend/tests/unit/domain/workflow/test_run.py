"""Run, NodeAttempt and Approval value objects (spec workflow FR-011..FR-038)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.domain.workflow.run import (
    ADHOC_KEY_PREFIX,
    TERMINAL_APPROVAL_STATUSES,
    TERMINAL_NODE_STATUSES,
    TERMINAL_RUN_STATUSES,
    Approval,
    ApprovalKind,
    ApprovalStatus,
    FailureReason,
    NodeAttempt,
    NodeStatus,
    Run,
    RunInput,
    RunInputKind,
    RunStatus,
    is_adhoc_key,
)

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": "run-1",
        "template_ref": "workflow:small-change",
        "template_snapshot": {"stages": []},
        "title": "Buffer table for int64 userid",
        "workdir": "/Users/dev/work/account",
        "machine_id": "laptop",
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def an_approval(**overrides: object) -> Approval:
    fields: dict[str, object] = {
        "id": "app-1",
        "run_id": "run-1",
        "kind": ApprovalKind.TOOL_CALL,
        "payload": {"project": "ACC", "summary": "Add buffer table"},
        "expires_at": NOW + timedelta(hours=1),
    }
    fields.update(overrides)
    return Approval(**fields)  # type: ignore[arg-type]


def test_the_status_vocabularies_are_exactly_the_documented_ones():
    assert {s.value for s in RunStatus} == {
        "draft",
        "running",
        "paused",
        "completed",
        "aborted",
        "failed",
    }
    assert {s.value for s in NodeStatus} == {
        "pending",
        "running",
        "waiting_review",
        "waiting_approval",
        "completed",
        "skipped",
        "failed",
    }
    assert {s.value for s in ApprovalStatus} == {
        "pending",
        "approved",
        "rejected",
        "expired",
        "superseded",
    }
    assert {k.value for k in ApprovalKind} == {"tool_call", "node_action"}
    assert {r.value for r in FailureReason} == {
        "interrupted",
        "agent_error",
        "missing_artifact",
        "attempt_ceiling",
    }
    assert {k.value for k in RunInputKind} == {"knowledge", "file", "link", "repo"}


def test_waiting_is_a_property_of_a_node_never_of_a_run():
    """FR-013: a run whose node sits in review is still `running`."""
    assert not any("waiting" in s.value for s in RunStatus)
    assert {s.value for s in NodeStatus if s.value.startswith("waiting")} == {
        "waiting_review",
        "waiting_approval",
    }


def test_a_failed_run_is_not_terminal_but_a_completed_or_aborted_one_is():
    assert {RunStatus.COMPLETED, RunStatus.ABORTED} == TERMINAL_RUN_STATUSES
    assert RunStatus.FAILED not in TERMINAL_RUN_STATUSES


def test_the_terminal_node_and_approval_sets():
    assert {
        NodeStatus.COMPLETED,
        NodeStatus.SKIPPED,
        NodeStatus.FAILED,
    } == TERMINAL_NODE_STATUSES
    assert ApprovalStatus.PENDING not in TERMINAL_APPROVAL_STATUSES
    assert len(TERMINAL_APPROVAL_STATUSES) == 4


def test_a_run_is_advanced_only_by_the_machine_that_owns_it():
    run = a_run(machine_id="laptop")
    assert run.owned_by("laptop") is True
    assert run.owned_by("desktop") is False


def test_a_new_run_starts_as_a_draft_at_version_one_with_no_position():
    run = a_run()
    assert run.status is RunStatus.DRAFT
    assert run.version == 1
    assert run.tokens_spent == 0
    assert (run.current_stage_key, run.current_node_key) == (None, None)
    assert run.inputs == ()


def test_a_run_carries_its_mounted_inputs():
    run = a_run(
        inputs=(
            RunInput(kind=RunInputKind.KNOWLEDGE, ref="account-service"),
            RunInput(kind=RunInputKind.LINK, ref="https://example.invalid/prd", label="PRD"),
        )
    )
    assert [i.kind for i in run.inputs] == [RunInputKind.KNOWLEDGE, RunInputKind.LINK]
    assert run.inputs[0].label is None
    assert run.inputs[1].label == "PRD"


@pytest.mark.parametrize(
    ("node_key", "adhoc"),
    [("implement", False), ("adhoc:second-repo", True), ("adhocish", False)],
)
def test_an_adhoc_task_is_recognised_by_its_key_namespace(node_key: str, adhoc: bool):
    assert is_adhoc_key(node_key) is adhoc
    attempt = NodeAttempt(
        id="att-1", run_id="run-1", stage_key="coding", node_key=node_key, attempt=1
    )
    assert attempt.is_adhoc is adhoc


def test_the_adhoc_prefix_cannot_collide_with_a_template_node_key():
    """A template key is a lowercase slug and may not contain ':' — which is
    exactly what the prefix uses."""
    assert ADHOC_KEY_PREFIX.endswith(":")


def test_a_fresh_attempt_is_pending_with_nothing_recorded_yet():
    attempt = NodeAttempt(
        id="att-1", run_id="run-1", stage_key="design", node_key="draft_td", attempt=1
    )
    assert attempt.status is NodeStatus.PENDING
    assert attempt.conversation_id is None
    assert attempt.failure_reason is None
    assert attempt.tokens == 0


def test_an_interrupted_attempt_keeps_its_conversation():
    """FR-027: reported, not resumed and not dropped — and still readable."""
    attempt = NodeAttempt(
        id="att-1",
        run_id="run-1",
        stage_key="coding",
        node_key="implement",
        attempt=1,
        status=NodeStatus.FAILED,
        conversation_id="conv-7",
        failure_reason=FailureReason.INTERRUPTED,
    )
    assert attempt.failure_reason is FailureReason.INTERRUPTED
    assert attempt.conversation_id == "conv-7"


def test_an_approval_starts_pending_and_authorises_nothing():
    approval = an_approval()
    assert approval.status is ApprovalStatus.PENDING
    assert approval.is_terminal is False
    assert approval.authorises_at(NOW) is False


def test_an_approved_unexpired_approval_authorises_its_write():
    approval = an_approval(status=ApprovalStatus.APPROVED)
    assert approval.is_terminal is True
    assert approval.authorises_at(NOW) is True


@pytest.mark.acceptance(spec="workflow", scenario="an expired approval does not authorise a write")
def test_an_approved_approval_past_its_expiry_authorises_nothing():
    """FR-037: expiry is answered by the clock, not by whether a sweep has run
    yet — otherwise a late sweep is a window in which an expired approval
    still carries a write."""
    approval = an_approval(status=ApprovalStatus.APPROVED, expires_at=NOW - timedelta(seconds=1))
    assert approval.authorises_at(NOW) is False


@pytest.mark.parametrize(
    "status",
    [ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED, ApprovalStatus.SUPERSEDED],
)
def test_no_other_terminal_state_authorises_a_write(status: ApprovalStatus):
    approval = an_approval(status=status)
    assert approval.is_terminal is True
    assert approval.authorises_at(NOW) is False


def test_an_approval_carries_the_arguments_verbatim():
    """A decision on a summary is not a decision — the payload is what will
    execute, whatever shape the agent passed."""
    payload = {"project": "ACC", "fields": {"labels": ["infra"], "nested": [1, 2, 3]}}
    approval = an_approval(payload=payload)
    assert approval.payload == payload
