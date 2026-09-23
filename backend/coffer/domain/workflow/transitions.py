"""The run and node state machines (spec workflow).

Every function here is pure: given a status and a command, it says what is legal
and what the next status is. Nothing reads a clock, a database or a file — which
is why the whole table can be tested transition by transition, and why the
application layer has exactly one place to ask "may this happen?".

The two rules worth stating up front, because they are the ones a delivery
engine usually gets wrong:

* **Nothing here sends a run backwards.** There is no route between stages
  ("Send work back by the developer's hand, never a template route"): a finding
  in a later task is acted on by retrying the task that was wrong or by adding
  one that fixes it, and either way the work that already passed keeps its
  result and its history. The judgement — redo the code, or redo the design —
  belongs to whoever holds the finding, and a table in this module could only
  make it in advance.
* A **ceiling** ends a loop ("Bound each task's attempts by its own ceiling"). A
  task may be tried the number of times it declared; the next try fails the run
  instead of spending the night on it.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from coffer.domain.workflow.errors import (
    AttemptCeilingReached,
    IllegalTransition,
    NotThisMachine,
    RunTerminal,
    WorkflowVersionConflict,
)
from coffer.domain.workflow.run import (
    TERMINAL_RUN_STATUSES,
    NodeAction,
    NodeStatus,
    RunSignal,
    RunStatus,
)
from coffer.domain.workflow.template import NodeType, WorkflowTemplate

_RUN_SIGNALS: dict[RunStatus, frozenset[RunSignal]] = {
    RunStatus.DRAFT: frozenset({RunSignal.START, RunSignal.ABORT}),
    RunStatus.RUNNING: frozenset({RunSignal.PAUSE, RunSignal.ABORT}),
    RunStatus.PAUSED: frozenset({RunSignal.RESUME, RunSignal.ABORT}),
    # A failed run is recoverable: the developer retries the node that failed
    # and resumes. It is not terminal — only `completed` and `aborted` are.
    RunStatus.FAILED: frozenset({RunSignal.RESUME, RunSignal.ABORT}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.ABORTED: frozenset(),
}

_RUN_RESULT: dict[RunSignal, RunStatus] = {
    RunSignal.START: RunStatus.RUNNING,
    RunSignal.PAUSE: RunStatus.PAUSED,
    RunSignal.RESUME: RunStatus.RUNNING,
    RunSignal.ABORT: RunStatus.ABORTED,
}

_NODE_ACTIONS: dict[NodeStatus, frozenset[NodeAction]] = {
    NodeStatus.PENDING: frozenset({NodeAction.START, NodeAction.SKIP}),
    # While a turn is in flight the node is the agent's; the levers are the
    # run's own pause and abort, not a node action racing the turn.
    NodeStatus.RUNNING: frozenset(),
    NodeStatus.WAITING_REVIEW: frozenset(
        {NodeAction.FEEDBACK, NodeAction.COMPLETE, NodeAction.RETRY, NodeAction.SKIP}
    ),
    # The approval decides this one. Retry and skip stay open so an expired or
    # rejected approval is an escape rather than a dead end.
    NodeStatus.WAITING_APPROVAL: frozenset({NodeAction.RETRY, NodeAction.SKIP}),
    NodeStatus.COMPLETED: frozenset({NodeAction.RETRY}),
    NodeStatus.SKIPPED: frozenset({NodeAction.RESTORE}),
    NodeStatus.FAILED: frozenset({NodeAction.RETRY, NodeAction.SKIP, NodeAction.RESTORE}),
}

_NODE_RESULT: dict[NodeAction, NodeStatus] = {
    NodeAction.START: NodeStatus.RUNNING,
    # Feedback re-opens the same attempt's turn — it is more to do, not a new
    # try. A new try is `retry`, which inserts attempt + 1 (spec workflow "Keep
    # every attempt when a node is retried").
    NodeAction.FEEDBACK: NodeStatus.RUNNING,
    NodeAction.COMPLETE: NodeStatus.COMPLETED,
    # A retry lands on a *new* attempt row, which starts pending and is picked
    # up by the advancer like any other pending node.
    NodeAction.RETRY: NodeStatus.PENDING,
    NodeAction.SKIP: NodeStatus.SKIPPED,
    NodeAction.RESTORE: NodeStatus.PENDING,
}


@dataclass(frozen=True)
class NodePosition:
    """Where a run is: a stage key and a node key."""

    stage_key: str
    node_key: str


def allowed_run_signals(status: RunStatus) -> frozenset[RunSignal]:
    """The signals a run in ``status`` accepts (spec workflow "Accept the run
    signals start, pause, resume and abort")."""
    return _RUN_SIGNALS[status]


def apply_run_signal(status: RunStatus, signal: RunSignal) -> RunStatus:
    """The status a signal leaves behind, or a refusal.

    Raises:
        RunTerminal: the run is completed or aborted — it refuses every
            mutating command, and that is a different answer from "not from
            this status" (spec workflow "Keep a run to six statuses",
            "Accept the run signals start, pause, resume and abort").
        IllegalTransition: the signal is not legal from a non-terminal status.
    """
    if status in TERMINAL_RUN_STATUSES:
        raise RunTerminal("run", status.value, signal.value)
    allowed = allowed_run_signals(status)
    if signal not in allowed:
        raise IllegalTransition(
            "run", status.value, signal.value, tuple(sorted(s.value for s in allowed))
        )
    return _RUN_RESULT[signal]


def ensure_run_mutable(status: RunStatus, attempted: str, run_id: str = "run") -> None:
    """Guard a mutating command that is not a run signal — a node action, an
    ad-hoc task, a main-thread message. A completed or aborted run refuses them
    all (spec workflow "Keep a run to six statuses", "Accept the run signals
    start, pause, resume and abort"), and a node action is no exception just
    because it names a node rather than the run."""
    if status in TERMINAL_RUN_STATUSES:
        raise RunTerminal(run_id, status.value, attempted)


def ensure_owning_machine(run_id: str, owner_machine_id: str, this_machine_id: str) -> None:
    """Only the machine that owns a run advances it (spec workflow "Advance a
    run only on the machine that owns it"). Everywhere else the run is visible
    and read-only."""
    if owner_machine_id != this_machine_id:
        raise NotThisMachine(run_id, owner_machine_id, this_machine_id)


def ensure_version(
    run_id: str,
    current: int,
    observed: int,
    *,
    status: RunStatus | None = None,
    stage_key: str | None = None,
    node_key: str | None = None,
) -> None:
    """Optimistic lock (spec workflow "Refuse a command carrying a stale
    version"): a stale observed version is refused with the run's current
    version and position, never merged."""
    if current != observed:
        raise WorkflowVersionConflict(
            run_id,
            expected=observed,
            current=current,
            status=None if status is None else status.value,
            stage_key=stage_key,
            node_key=node_key,
        )


def allowed_node_actions(node_status: NodeStatus, node_type: NodeType) -> frozenset[NodeAction]:
    """The actions a node in ``node_status`` accepts (spec workflow "Accept the
    node actions start, feedback, complete, retry, skip and restore").

    The node's type narrows one thing: ``feedback`` is a message to an agent
    mid-turn, and a ``manual`` node has no agent and no turn — there is nothing
    for the feedback to reach. Every other action means the same for every
    type, because a manual node is still a step that can be completed, skipped,
    retried or restored.
    """
    actions = _NODE_ACTIONS[node_status]
    if node_type is NodeType.MANUAL:
        return actions - {NodeAction.FEEDBACK}
    return actions


def apply_node_action(
    node_status: NodeStatus, action: NodeAction, node_type: NodeType
) -> NodeStatus:
    """The node status an action leaves behind, or a refusal.

    ``retry`` returns ``pending`` rather than ``running``: the retry opens a new
    attempt row, and the attempt that is starting is pending until the advancer
    dispatches its turn. The failed attempt keeps its own status and its
    conversation (spec workflow "Keep every attempt when a node is retried").

    Raises:
        IllegalTransition: the action is not legal for this status and type.
    """
    allowed = allowed_node_actions(node_status, node_type)
    if action not in allowed:
        raise IllegalTransition(
            f"node ({node_type.value})",
            node_status.value,
            action.value,
            tuple(sorted(a.value for a in allowed)),
        )
    return _NODE_RESULT[action]


def next_node(
    template: WorkflowTemplate,
    completed_keys: Collection[str],
    *,
    skipped_keys: Collection[str] = (),
) -> NodePosition | None:
    """The next node to run, or ``None`` when the run is finished.

    The rule is one line on purpose: walk the template in order and return the
    first node that is not done. A task the developer reopened is not done, so
    the same walk hands it back and then walks forward past everything that
    still is — which is the whole of what "send it back" needs to mean now that
    no route in the template claims to do it (spec workflow "Send work back by
    the developer's hand, never a template route").

    A skipped node counts as done for ordering: it will not run, so the run
    must not stop on it. An optional stage is *not* skipped here — ``optional``
    says the developer may skip it, and skipping is an action they take, not
    something the walk decides for them.
    """
    done = set(completed_keys) | set(skipped_keys)
    for stage, node in template.ordered_nodes():
        if node.key not in done:
            return NodePosition(stage_key=stage.key, node_key=node.key)
    return None


def check_attempt_ceiling(node_key: str, attempts_used: int, ceiling: int) -> int:
    """The attempt number a retry would open, or a refusal at the ceiling.

    One task's tries against that task's own ceiling (spec workflow "Bound each
    task's attempts by its own ceiling"). The limit belongs to the task rather
    than to the workflow, because a draft that is cheap to redo and a deploy
    that must not be tried twice are not the same judgement.

    Raises:
        AttemptCeilingReached: when the next attempt would exceed the ceiling.
    """
    attempt = attempts_used + 1
    if attempt > ceiling:
        raise AttemptCeilingReached(node_key, ceiling)
    return attempt
