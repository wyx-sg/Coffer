"""The event vocabulary and the projection fold (spec workflow FR-014, FR-018).

The fold is what rebuilds a run after a restart, so it is tested the way a
restart exercises it: against a handwritten event list, with no run object in
sight.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.domain.workflow.events import (
    ActorKind,
    EventActor,
    EventType,
    RunProjection,
    WorkflowEvent,
    project,
)
from coffer.domain.workflow.run import RunStatus

#: The closed set data-model.md lists, written out by hand. If a member is
#: added or removed without the spec changing, this test says so.
DOCUMENTED_EVENT_TYPES = {
    "run.created",
    "run.started",
    "run.paused",
    "run.resumed",
    "run.aborted",
    "run.completed",
    "run.failed",
    "node.started",
    "node.output_ready",
    "node.feedback_submitted",
    "node.completed",
    "node.failed",
    "node.retried",
    "node.skipped",
    "node.restored",
    "node.adhoc_added",
    "node.briefed",
    "approval.created",
    "approval.approved",
    "approval.rejected",
    "approval.expired",
    "artifact.added",
}


def test_the_event_vocabulary_is_exactly_the_documented_closed_set():
    assert {e.value for e in EventType} == DOCUMENTED_EVENT_TYPES


def test_there_is_no_waiting_review_event():
    """Waiting is the absence of a next event, not an event — the one
    simplification this spec takes over its prior art."""
    assert "node.waiting_review" not in {e.value for e in EventType}
    assert not any("waiting" in e.value for e in EventType)


def _event(
    sequence: int,
    event_type: EventType,
    *,
    stage: str | None = None,
    node: str | None = None,
    payload: dict[str, Any] | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        sequence=sequence,
        event_type=event_type,
        stage_key=stage,
        node_key=node,
        payload=payload or {},
    )


def test_no_events_projects_a_draft_run_at_no_position():
    assert project([]) == RunProjection(
        status=RunStatus.DRAFT,
        current_stage_key=None,
        current_node_key=None,
        tokens_spent=0,
    )


@pytest.mark.acceptance(spec="workflow", scenario="a run rebuilds itself from its events")
def test_a_run_mid_flight_projects_its_status_and_position():
    projection = project(
        [
            _event(1, EventType.RUN_CREATED),
            _event(2, EventType.RUN_STARTED),
            _event(3, EventType.NODE_STARTED, stage="design", node="draft_td"),
            _event(
                4,
                EventType.NODE_COMPLETED,
                stage="design",
                node="draft_td",
                payload={"tokens": 1200},
            ),
            _event(5, EventType.NODE_STARTED, stage="coding", node="implement"),
        ]
    )
    assert projection == RunProjection(
        status=RunStatus.RUNNING,
        current_stage_key="coding",
        current_node_key="implement",
        tokens_spent=1200,
    )


def test_the_fold_is_ordered_by_sequence_not_by_arrival():
    """A repository that reads events back unordered must not produce a
    different run than one that reads them ordered."""
    events = [
        _event(3, EventType.NODE_STARTED, stage="coding", node="implement"),
        _event(1, EventType.RUN_CREATED),
        _event(2, EventType.RUN_STARTED),
    ]
    assert project(events) == project(sorted(events, key=lambda e: e.sequence))
    assert project(events).current_node_key == "implement"


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        (EventType.RUN_CREATED, RunStatus.DRAFT),
        (EventType.RUN_STARTED, RunStatus.RUNNING),
        (EventType.RUN_PAUSED, RunStatus.PAUSED),
        (EventType.RUN_RESUMED, RunStatus.RUNNING),
        (EventType.RUN_ABORTED, RunStatus.ABORTED),
        (EventType.RUN_COMPLETED, RunStatus.COMPLETED),
        (EventType.RUN_FAILED, RunStatus.FAILED),
    ],
)
def test_each_run_event_projects_its_status(event_type: EventType, expected: RunStatus):
    assert project([_event(1, event_type)]).status is expected


@pytest.mark.parametrize(
    "event_type",
    [
        EventType.NODE_STARTED,
        EventType.NODE_OUTPUT_READY,
        EventType.NODE_FEEDBACK_SUBMITTED,
        EventType.NODE_COMPLETED,
        EventType.NODE_FAILED,
        EventType.NODE_RETRIED,
        EventType.NODE_SKIPPED,
        EventType.NODE_RESTORED,
    ],
)
def test_a_node_event_moves_the_position_without_touching_the_status(event_type: EventType):
    projection = project(
        [
            _event(1, EventType.RUN_STARTED),
            _event(2, event_type, stage="coding", node="implement"),
        ]
    )
    assert (projection.current_stage_key, projection.current_node_key) == ("coding", "implement")
    assert projection.status is RunStatus.RUNNING


@pytest.mark.parametrize(
    "event_type",
    [
        EventType.APPROVAL_CREATED,
        EventType.APPROVAL_APPROVED,
        EventType.APPROVAL_REJECTED,
        EventType.APPROVAL_EXPIRED,
        EventType.ARTIFACT_ADDED,
        EventType.NODE_ADHOC_ADDED,
    ],
)
def test_a_record_only_event_changes_neither_status_nor_position(event_type: EventType):
    before = [
        _event(1, EventType.RUN_STARTED),
        _event(2, EventType.NODE_STARTED, stage="design", node="draft_td"),
    ]
    assert project([*before, _event(3, event_type, stage="design", node="draft_td")]) == project(
        before
    )


def test_a_failed_run_keeps_the_node_it_stopped_at():
    projection = project(
        [
            _event(1, EventType.RUN_STARTED),
            _event(2, EventType.NODE_STARTED, stage="coding", node="implement"),
            _event(
                3,
                EventType.NODE_FAILED,
                stage="coding",
                node="implement",
                payload={"reason": "interrupted"},
            ),
            _event(4, EventType.RUN_FAILED),
        ]
    )
    assert projection.status is RunStatus.FAILED
    assert projection.current_node_key == "implement"


def test_a_completed_run_is_at_no_node():
    projection = project(
        [
            _event(1, EventType.RUN_STARTED),
            _event(2, EventType.NODE_STARTED, stage="testing", node="verify"),
            _event(3, EventType.NODE_COMPLETED, stage="testing", node="verify"),
            _event(4, EventType.RUN_COMPLETED),
        ]
    )
    assert projection.status is RunStatus.COMPLETED
    assert projection.current_stage_key is None
    assert projection.current_node_key is None


def test_a_node_event_without_keys_leaves_the_position_alone():
    projection = project(
        [
            _event(1, EventType.NODE_STARTED, stage="design", node="draft_td"),
            _event(2, EventType.NODE_COMPLETED),
        ]
    )
    assert (projection.current_stage_key, projection.current_node_key) == ("design", "draft_td")


def test_tokens_are_summed_across_every_event_that_reports_them():
    projection = project(
        [
            _event(1, EventType.NODE_COMPLETED, node="a", payload={"tokens": 100}),
            _event(2, EventType.NODE_FAILED, node="b", payload={"tokens": 250}),
            _event(3, EventType.NODE_COMPLETED, node="b", payload={"tokens": 50}),
        ]
    )
    assert projection.tokens_spent == 400


@pytest.mark.parametrize("bad", [None, "1200", True, -5, 12.5, {"total": 5}])
def test_a_payload_that_is_not_a_token_count_adds_nothing(bad: Any):
    projection = project([_event(1, EventType.NODE_COMPLETED, payload={"tokens": bad})])
    assert projection.tokens_spent == 0


def test_a_retry_after_a_failure_projects_the_run_back_to_its_node():
    """FR-027 then FR-022: the interrupted node is reported, and the retry that
    follows is an ordinary event the fold reads like any other."""
    projection = project(
        [
            _event(1, EventType.RUN_STARTED),
            _event(2, EventType.NODE_STARTED, stage="coding", node="implement"),
            _event(
                3,
                EventType.NODE_FAILED,
                stage="coding",
                node="implement",
                payload={"reason": "interrupted", "tokens": 700},
            ),
            _event(4, EventType.RUN_FAILED),
            _event(5, EventType.RUN_RESUMED),
            _event(
                6, EventType.NODE_RETRIED, stage="coding", node="implement", payload={"attempt": 2}
            ),
        ]
    )
    assert projection == RunProjection(
        status=RunStatus.RUNNING,
        current_stage_key="coding",
        current_node_key="implement",
        tokens_spent=700,
    )


def test_an_event_carries_its_actor_for_the_audit():
    actor = EventActor(actor_kind=ActorKind.WORKFLOW, source_surface="daemon")
    event = WorkflowEvent(sequence=1, event_type=EventType.NODE_STARTED, actor=actor)
    assert event.actor is not None
    assert event.actor.actor_kind is ActorKind.WORKFLOW
    assert event.actor.actor_id is None
    assert {a.value for a in ActorKind} == {"user", "workflow", "agent", "system"}
