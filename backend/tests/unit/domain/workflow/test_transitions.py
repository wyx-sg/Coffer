"""The run and node state machines (spec workflow FR-013..FR-026).

Table-driven both ways: every legal transition asserts the status it leaves
behind, and every illegal one asserts the refusal. The illegal half is the half
that matters — a state machine that only proves what it allows has not been
tested.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.domain.workflow.errors import (
    AttemptCeilingReached,
    IllegalTransition,
    NotThisMachine,
    RunTerminal,
    WorkflowVersionConflict,
)
from coffer.domain.workflow.run import NodeAction, NodeStatus, RunSignal, RunStatus
from coffer.domain.workflow.template import NodeType, parse_template
from coffer.domain.workflow.transitions import (
    allowed_node_actions,
    allowed_run_signals,
    apply_node_action,
    apply_run_signal,
    check_attempt_ceiling,
    ensure_owning_machine,
    ensure_run_mutable,
    ensure_version,
    next_node,
    resolve_feedback_edge,
    take_feedback_edge,
)

from .test_template import valid_config


def template() -> Any:
    return parse_template(valid_config())


# --------------------------------------------------------------------------
# Run signals (FR-016)
# --------------------------------------------------------------------------

LEGAL_RUN: list[tuple[RunStatus, RunSignal, RunStatus]] = [
    (RunStatus.DRAFT, RunSignal.START, RunStatus.RUNNING),
    (RunStatus.DRAFT, RunSignal.ABORT, RunStatus.ABORTED),
    (RunStatus.RUNNING, RunSignal.PAUSE, RunStatus.PAUSED),
    (RunStatus.RUNNING, RunSignal.ABORT, RunStatus.ABORTED),
    (RunStatus.PAUSED, RunSignal.RESUME, RunStatus.RUNNING),
    (RunStatus.PAUSED, RunSignal.ABORT, RunStatus.ABORTED),
    (RunStatus.FAILED, RunSignal.RESUME, RunStatus.RUNNING),
    (RunStatus.FAILED, RunSignal.ABORT, RunStatus.ABORTED),
]


@pytest.mark.parametrize(
    ("status", "signal", "expected"),
    [pytest.param(s, sig, e, id=f"{s.value}-{sig.value}") for s, sig, e in LEGAL_RUN],
)
def test_a_legal_run_signal_lands_on_its_status(
    status: RunStatus, signal: RunSignal, expected: RunStatus
):
    assert signal in allowed_run_signals(status)
    assert apply_run_signal(status, signal) is expected


ILLEGAL_RUN: list[tuple[RunStatus, RunSignal]] = [
    (RunStatus.DRAFT, RunSignal.PAUSE),
    (RunStatus.DRAFT, RunSignal.RESUME),
    (RunStatus.RUNNING, RunSignal.START),
    (RunStatus.RUNNING, RunSignal.RESUME),
    (RunStatus.PAUSED, RunSignal.START),
    (RunStatus.PAUSED, RunSignal.PAUSE),
    (RunStatus.FAILED, RunSignal.START),
    (RunStatus.FAILED, RunSignal.PAUSE),
]


@pytest.mark.parametrize(
    ("status", "signal"),
    [pytest.param(s, sig, id=f"{s.value}-{sig.value}") for s, sig in ILLEGAL_RUN],
)
def test_an_illegal_run_signal_is_refused_with_what_was_allowed(
    status: RunStatus, signal: RunSignal
):
    assert signal not in allowed_run_signals(status)
    with pytest.raises(IllegalTransition) as caught:
        apply_run_signal(status, signal)
    assert caught.value.status == status.value
    assert caught.value.attempted == signal.value
    assert set(caught.value.allowed) == {s.value for s in allowed_run_signals(status)}


@pytest.mark.parametrize("status", [RunStatus.COMPLETED, RunStatus.ABORTED])
@pytest.mark.parametrize("signal", list(RunSignal))
def test_a_completed_or_aborted_run_refuses_every_signal(status: RunStatus, signal: RunSignal):
    """FR-013 / FR-016 — and it is `RunTerminal`, not `IllegalTransition`: the
    answer is "never again", not "not from here"."""
    assert allowed_run_signals(status) == frozenset()
    with pytest.raises(RunTerminal) as caught:
        apply_run_signal(status, signal)
    assert caught.value.status == status.value
    assert caught.value.attempted == signal.value


@pytest.mark.parametrize("status", [RunStatus.COMPLETED, RunStatus.ABORTED])
def test_a_terminal_run_refuses_mutating_commands_that_are_not_signals(status: RunStatus):
    with pytest.raises(RunTerminal) as caught:
        ensure_run_mutable(status, "node.complete", run_id="run-1")
    assert caught.value.run_id == "run-1"
    assert caught.value.attempted == "node.complete"


@pytest.mark.parametrize(
    "status", [RunStatus.DRAFT, RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.FAILED]
)
def test_a_live_run_accepts_mutating_commands(status: RunStatus):
    ensure_run_mutable(status, "node.complete")  # does not raise


def test_every_run_status_has_a_signal_row():
    """A status with no row would raise KeyError at the surface rather than
    refusing cleanly, so the table must cover the enum."""
    for status in RunStatus:
        assert isinstance(allowed_run_signals(status), frozenset)


# --------------------------------------------------------------------------
# Ownership and the optimistic lock (FR-012, FR-015)
# --------------------------------------------------------------------------


def test_the_owning_machine_may_advance_the_run():
    ensure_owning_machine("run-1", "laptop", "laptop")  # does not raise


@pytest.mark.acceptance(
    spec="workflow", scenario="a run is read-only on a machine that does not own it"
)
def test_another_machine_is_refused_and_told_who_owns_it():
    with pytest.raises(NotThisMachine) as caught:
        ensure_owning_machine("run-1", "laptop", "desktop")
    assert caught.value.owner_machine_id == "laptop"
    assert caught.value.this_machine_id == "desktop"
    assert "laptop" in str(caught.value)


def test_a_matching_version_passes():
    ensure_version("run-1", 4, 4)  # does not raise


def test_a_stale_version_is_refused_with_the_runs_current_position():
    with pytest.raises(WorkflowVersionConflict) as caught:
        ensure_version(
            "run-1",
            5,
            4,
            status=RunStatus.RUNNING,
            stage_key="coding",
            node_key="implement",
        )
    assert (caught.value.current, caught.value.expected) == (5, 4)
    assert caught.value.status == "running"
    assert (caught.value.stage_key, caught.value.node_key) == ("coding", "implement")


# --------------------------------------------------------------------------
# Node actions (FR-020, FR-021)
# --------------------------------------------------------------------------

LEGAL_NODE: list[tuple[NodeStatus, NodeAction, NodeStatus]] = [
    (NodeStatus.PENDING, NodeAction.START, NodeStatus.RUNNING),
    (NodeStatus.PENDING, NodeAction.SKIP, NodeStatus.SKIPPED),
    (NodeStatus.WAITING_REVIEW, NodeAction.FEEDBACK, NodeStatus.RUNNING),
    (NodeStatus.WAITING_REVIEW, NodeAction.COMPLETE, NodeStatus.COMPLETED),
    (NodeStatus.WAITING_REVIEW, NodeAction.RETRY, NodeStatus.PENDING),
    (NodeStatus.WAITING_REVIEW, NodeAction.SKIP, NodeStatus.SKIPPED),
    (NodeStatus.WAITING_APPROVAL, NodeAction.RETRY, NodeStatus.PENDING),
    (NodeStatus.WAITING_APPROVAL, NodeAction.SKIP, NodeStatus.SKIPPED),
    (NodeStatus.COMPLETED, NodeAction.RETRY, NodeStatus.PENDING),
    (NodeStatus.SKIPPED, NodeAction.RESTORE, NodeStatus.PENDING),
    (NodeStatus.FAILED, NodeAction.RETRY, NodeStatus.PENDING),
    (NodeStatus.FAILED, NodeAction.SKIP, NodeStatus.SKIPPED),
    (NodeStatus.FAILED, NodeAction.RESTORE, NodeStatus.PENDING),
]


@pytest.mark.parametrize(
    ("status", "action", "expected"),
    [pytest.param(s, a, e, id=f"{s.value}-{a.value}") for s, a, e in LEGAL_NODE],
)
def test_a_legal_node_action_lands_on_its_status(
    status: NodeStatus, action: NodeAction, expected: NodeStatus
):
    assert action in allowed_node_actions(status, NodeType.AI)
    assert apply_node_action(status, action, NodeType.AI) is expected


def _illegal_node_pairs() -> list[tuple[NodeStatus, NodeAction]]:
    legal = {(s, a) for s, a, _ in LEGAL_NODE}
    return [(s, a) for s in NodeStatus for a in NodeAction if (s, a) not in legal]


@pytest.mark.parametrize(
    ("status", "action"),
    [pytest.param(s, a, id=f"{s.value}-{a.value}") for s, a in _illegal_node_pairs()],
)
def test_every_other_node_pair_is_refused(status: NodeStatus, action: NodeAction):
    """The complement of the legal table — so adding a transition to the state
    machine without adding it to `LEGAL_NODE` fails here rather than passing
    unnoticed."""
    with pytest.raises(IllegalTransition) as caught:
        apply_node_action(status, action, NodeType.AI)
    assert caught.value.status == status.value
    assert caught.value.attempted == action.value


def test_a_running_node_takes_no_action_at_all():
    """While a turn is in flight the levers are the run's pause and abort."""
    assert allowed_node_actions(NodeStatus.RUNNING, NodeType.AI) == frozenset()


def test_a_retry_lands_on_pending_because_it_opens_a_new_attempt():
    """FR-022: the failed attempt keeps its own status and conversation; the
    attempt that is starting is pending until the advancer dispatches it."""
    assert apply_node_action(NodeStatus.FAILED, NodeAction.RETRY, NodeType.AI) is NodeStatus.PENDING


def test_a_manual_node_cannot_be_given_feedback():
    """There is no agent and no turn for the feedback to reach."""
    assert NodeAction.FEEDBACK not in allowed_node_actions(
        NodeStatus.WAITING_REVIEW, NodeType.MANUAL
    )
    with pytest.raises(IllegalTransition):
        apply_node_action(NodeStatus.WAITING_REVIEW, NodeAction.FEEDBACK, NodeType.MANUAL)


def test_an_ai_task_may_be_given_feedback():
    assert apply_node_action(NodeStatus.WAITING_REVIEW, NodeAction.FEEDBACK, NodeType.AI) is (
        NodeStatus.RUNNING
    )


@pytest.mark.parametrize("node_type", list(NodeType))
def test_only_feedback_is_narrowed_by_the_node_type(node_type: NodeType):
    """A manual step is still a step: it completes, skips, retries and restores
    like any other — only feedback is narrowed by the type.

    Parametrised over the WHOLE enum rather than a list written out here, so a
    type added later is covered by this claim the moment it exists instead of
    quietly sitting outside it."""
    for status in NodeStatus:
        expected = allowed_node_actions(status, NodeType.AI) - (
            {NodeAction.FEEDBACK} if node_type is NodeType.MANUAL else set()
        )
        assert allowed_node_actions(status, node_type) == expected


# --------------------------------------------------------------------------
# Walking the template (FR-017, FR-025)
# --------------------------------------------------------------------------


def test_a_fresh_run_starts_at_the_first_node_of_the_first_stage():
    position = next_node(template(), completed_keys=())
    assert position is not None
    assert (position.stage_key, position.node_key) == ("design", "draft_td")


def test_the_walk_moves_on_as_nodes_complete():
    position = next_node(template(), completed_keys={"draft_td"})
    assert position is not None
    assert (position.stage_key, position.node_key) == ("coding", "implement")


def test_a_skipped_node_does_not_stop_the_walk():
    position = next_node(template(), completed_keys={"draft_td"}, skipped_keys={"implement"})
    assert position is not None
    assert position.node_key == "verify"


def test_the_walk_ends_when_every_node_is_done():
    assert next_node(template(), completed_keys={"draft_td", "implement", "verify"}) is None


def test_the_walk_returns_to_a_reopened_node_and_then_skips_what_is_still_done():
    """FR-025 in two moves: `implement` was reopened, so the walk hands it back;
    once it completes again the walk goes to `verify`, not back to `draft_td`."""
    completed = {"draft_td", "verify"}
    reopened = next_node(template(), completed_keys=completed)
    assert reopened is not None and reopened.node_key == "implement"
    after = next_node(template(), completed_keys=completed | {"implement"})
    assert after is None


# --------------------------------------------------------------------------
# Feedback edges and the ceiling (FR-025, FR-026)
# --------------------------------------------------------------------------


def test_an_edge_resolves_on_an_exact_stage_and_reason():
    edge = resolve_feedback_edge(template(), "testing", "code_issue")
    assert edge is not None and edge.to_stage == "coding"


@pytest.mark.parametrize(
    ("from_stage", "reason"),
    [
        ("testing", "design_issue"),  # right stage, no such reason
        ("coding", "code_issue"),  # right reason, no edge leaves this stage
        ("release", "code_issue"),  # no such stage
    ],
)
def test_a_near_miss_resolves_to_nothing_rather_than_a_guess(from_stage: str, reason: str):
    assert resolve_feedback_edge(template(), from_stage, reason) is None


@pytest.mark.acceptance(
    spec="workflow", scenario="sending work back adds a task and resets nothing"
)
def test_taking_an_edge_puts_a_new_task_in_the_target_stage():
    outcome = take_feedback_edge(
        template(),
        "testing",
        "code_issue",
        task_key="adhoc:code-issue",
        firings_used=0,
    )
    assert outcome.target.stage_key == "coding"
    assert outcome.target.node_key == "adhoc:code-issue"
    assert outcome.firing == 1
    # Nothing that ran is named: the outcome has no way to express "reopen
    # `implement`", which is FR-025 held up by the type rather than by care.
    assert not hasattr(outcome, "reopened_keys")


def test_taking_an_edge_the_template_does_not_have_is_refused():
    with pytest.raises(IllegalTransition) as caught:
        take_feedback_edge(
            template(),
            "testing",
            "design_issue",
            task_key="adhoc:design-issue",
            firings_used=0,
        )
    assert caught.value.attempted == "design_issue"
    assert caught.value.allowed == ("code_issue->coding",)


@pytest.mark.acceptance(
    spec="workflow", scenario="a loop between two stages stops at the attempt ceiling"
)
def test_the_ceiling_ends_the_loop_instead_of_adding_another_task():
    """FR-026: testing sends work back to coding three times; the fourth fails
    the run with the reason."""
    with pytest.raises(AttemptCeilingReached) as caught:
        take_feedback_edge(
            template(),
            "testing",
            "code_issue",
            task_key="adhoc:code-issue-4",
            firings_used=3,  # the template's ceiling
        )
    # The refusal names the task it declined to create, not a node that passed.
    assert caught.value.node_key == "adhoc:code-issue-4"
    assert caught.value.ceiling == 3


def test_the_last_firing_under_the_ceiling_is_still_allowed():
    outcome = take_feedback_edge(
        template(),
        "testing",
        "code_issue",
        task_key="adhoc:code-issue-3",
        firings_used=2,
    )
    assert outcome.firing == 3


def test_a_retry_and_a_feedback_edge_stop_at_the_same_number():
    assert check_attempt_ceiling("implement", 2, 3) == 3
    with pytest.raises(AttemptCeilingReached) as caught:
        check_attempt_ceiling("implement", 3, 3)
    assert caught.value.ceiling == 3


def test_a_ceiling_of_one_permits_the_first_attempt_and_no_retry():
    assert check_attempt_ceiling("implement", 0, 1) == 1
    with pytest.raises(AttemptCeilingReached):
        check_attempt_ceiling("implement", 1, 1)
