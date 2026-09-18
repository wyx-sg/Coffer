"""The closed event vocabulary and the projection fold (spec workflow).

A run's append-only event log is its record of truth (FR-014); its status,
stage, node and spend are a projection of that log, carried on the run row only
so a list query is one row read. :func:`project` is that fold, and it is what
rebuilds every run on daemon start.

The fold is deliberately pure and takes a plain sequence: the restart test is
"build a run, drop the projection, rebuild from events, compare", and that test
is only worth anything if the rebuild path is the same code the daemon runs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from coffer.domain.workflow.run import RunStatus


class ActorKind(StrEnum):
    """Who caused an event. ``workflow`` is the engine advancing a run on its
    own — distinct from ``system`` (the daemon restarting, an approval
    expiring) because "the run moved itself" and "the process happened to it"
    read differently in an audit."""

    USER = "user"
    WORKFLOW = "workflow"
    AGENT = "agent"
    SYSTEM = "system"


@dataclass(frozen=True)
class EventActor:
    """The ``actor`` column's shape: who, and through which surface."""

    actor_kind: ActorKind
    source_surface: str
    actor_id: str | None = None


class EventType(StrEnum):
    """The whole event vocabulary — a closed set.

    There is deliberately **no** ``node.waiting_review``: waiting is the
    absence of a next event, not an event. Recording it would create a second
    place where "this node is waiting" is written down, and the two would
    eventually disagree.
    """

    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    RUN_ABORTED = "run.aborted"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    NODE_STARTED = "node.started"
    NODE_OUTPUT_READY = "node.output_ready"
    NODE_FEEDBACK_SUBMITTED = "node.feedback_submitted"
    NODE_COMPLETED = "node.completed"
    NODE_FAILED = "node.failed"
    NODE_RETRIED = "node.retried"
    NODE_SKIPPED = "node.skipped"
    NODE_RESTORED = "node.restored"
    NODE_ADHOC_ADDED = "node.adhoc_added"
    #: The developer wrote something for a task that has not started yet — a
    #: brief, queued onto the attempt the task will open with (FR-068). It is
    #: NOT a position event: saying what a later task should do does not move
    #: the run to it.
    NODE_BRIEFED = "node.briefed"
    APPROVAL_CREATED = "approval.created"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    APPROVAL_EXPIRED = "approval.expired"
    ARTIFACT_ADDED = "artifact.added"


@dataclass(frozen=True)
class WorkflowEvent:
    """One entry in a run's log.

    ``sequence`` is monotonic per run and is what the fold orders by — not
    ``created_at``, whose resolution is not guaranteed to separate two events
    appended in the same transaction.
    """

    sequence: int
    event_type: EventType
    stage_key: str | None = None
    node_key: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    actor: EventActor | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class RunProjection:
    """What the fold produces: the four columns the run row caches."""

    status: RunStatus = RunStatus.DRAFT
    current_stage_key: str | None = None
    current_node_key: str | None = None
    tokens_spent: int = 0


#: Events that set the run's status outright. Everything else either moves the
#: position, adds spend, or is a record with no bearing on the projection.
_STATUS_BY_EVENT: dict[EventType, RunStatus] = {
    EventType.RUN_CREATED: RunStatus.DRAFT,
    EventType.RUN_STARTED: RunStatus.RUNNING,
    EventType.RUN_PAUSED: RunStatus.PAUSED,
    EventType.RUN_RESUMED: RunStatus.RUNNING,
    EventType.RUN_ABORTED: RunStatus.ABORTED,
    EventType.RUN_COMPLETED: RunStatus.COMPLETED,
    EventType.RUN_FAILED: RunStatus.FAILED,
    # Exceeding the budget pauses the run rather than continuing to spend
    # (FR-018) — the event is its own type so the reason survives, but the
    # status it leaves behind is an ordinary pause.
}

#: Events that move the run's position to the node they name. A node that
#: finished still *is* the position until the next one starts: that is what
#: "where the run stopped" means for a failed or aborted run.
_POSITION_EVENTS: frozenset[EventType] = frozenset(
    {
        EventType.NODE_STARTED,
        EventType.NODE_OUTPUT_READY,
        EventType.NODE_FEEDBACK_SUBMITTED,
        EventType.NODE_COMPLETED,
        EventType.NODE_FAILED,
        EventType.NODE_RETRIED,
        EventType.NODE_SKIPPED,
        EventType.NODE_RESTORED,
    }
)


def project(events: Iterable[WorkflowEvent]) -> RunProjection:
    """Fold a run's events into its status, position and spend (FR-014).

    Events are folded in ``sequence`` order regardless of the order they arrive
    in, so a repository that reads them back unordered cannot produce a
    different run than one that reads them ordered.

    Spend is summed from every event carrying an integer ``tokens`` payload
    field — the writer puts it on a node's terminal event, and summing rather
    than overwriting is what makes the total survive an event appended out of
    band.
    """
    status = RunStatus.DRAFT
    stage_key: str | None = None
    node_key: str | None = None
    tokens = 0

    for event in sorted(events, key=lambda e: e.sequence):
        mapped = _STATUS_BY_EVENT.get(event.event_type)
        if mapped is not None:
            status = mapped
        if event.event_type is EventType.RUN_COMPLETED:
            # A completed run is not *at* a node; leaving the last one set
            # would show a finished run as sitting somewhere.
            stage_key = None
            node_key = None
        elif event.event_type in _POSITION_EVENTS:
            if event.stage_key is not None:
                stage_key = event.stage_key
            if event.node_key is not None:
                node_key = event.node_key
        tokens += _tokens(event.payload)

    return RunProjection(
        status=status,
        current_stage_key=stage_key,
        current_node_key=node_key,
        tokens_spent=tokens,
    )


def _tokens(payload: Mapping[str, Any]) -> int:
    value = payload.get("tokens")
    # bool is an int in Python, and a `tokens: true` payload is a bug rather
    # than one token.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value
