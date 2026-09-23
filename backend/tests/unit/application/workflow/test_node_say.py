"""Talking to a task, at each point in its life (spec workflow "Let the developer
speak to a task at any point, in one place").

One composer, four meanings, and the meaning is the ENGINE's to decide — a
surface that worked it out from a status it read three seconds ago would
eventually queue a brief onto a task that had already started.
"""

from __future__ import annotations

import pytest

from coffer.domain.workflow.errors import AttemptCeilingReached, IllegalTransition
from coffer.domain.workflow.run import NodeAction, NodeStatus

from .conftest import TEMPLATE, Engine, build_engine, with_ceiling, with_template


@pytest.mark.acceptance(spec="workflow", scenario="a task can be told something before it starts")
async def test_a_task_the_run_has_not_reached_carries_what_it_was_told(engine: Engine) -> None:
    """The brief is written before the task, not shouted after it."""
    run = await engine.started()

    await engine.nodes.say(run.id, "write_code", text="  use the 0088 migration style  ")

    queued = await engine.attempts.latest_attempt(run.id, "write_code")
    assert queued is not None
    assert queued.attempt == 1
    assert queued.status == NodeStatus.PENDING.value
    assert queued.instructions == "use the 0088 migration style"
    assert engine.types(run.id)[-1] == "node.briefed"
    # Saying what a LATER task should do must not claim the run is at it.
    current = await engine.run_repo.get_run(run.id)
    assert current.current_node_key != "write_code"


async def test_a_second_thought_is_added_rather_than_substituted(engine: Engine) -> None:
    run = await engine.started()
    await engine.nodes.say(run.id, "write_code", text="use the 0088 style")
    await engine.nodes.say(run.id, "write_code", text="and leave the fixtures alone")

    queued = await engine.attempts.latest_attempt(run.id, "write_code")
    assert queued.instructions == "use the 0088 style\n\nand leave the fixtures alone"


async def test_what_was_queued_reaches_the_task_when_it_starts(engine: Engine) -> None:
    """The brief is the point; a column nothing reads would be decoration."""
    run = await engine.started()
    await engine.nodes.say(run.id, "draft_td", text="follow the 0088 migration style")
    current = await engine.run_repo.get_run(run.id)

    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=current.version)

    assert engine.dispatcher.last.attempt.instructions == "follow the 0088 migration style"


async def test_a_task_waiting_for_review_carries_the_same_attempt_on(engine: Engine) -> None:
    run = await engine.started()
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    await engine.nodes.record_output(run.id, "draft_td", summary="drafted")

    await engine.nodes.say(run.id, "draft_td", text="cover the migration too")

    row = await engine.attempts.latest_attempt(run.id, "draft_td")
    assert row.attempt == 1, "more to do opened a new attempt"
    assert row.status == NodeStatus.RUNNING.value
    assert engine.types(run.id)[-1] == "node.feedback_submitted"
    assert engine.dispatcher.last.follow_up == "cover the migration too"


@pytest.mark.acceptance(spec="workflow", scenario="talking to a finished task reopens it")
async def test_talking_to_a_completed_task_opens_its_next_attempt(engine: Engine) -> None:
    """A task the developer is still talking to is not finished."""
    run = await engine.started()
    engine.artifacts.add(run.id, "draft_td", 1, "td.md")
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    # The node's policy is `never`, so a reported output with its artifact on
    # disk completes it outright — no review to sit in.
    await engine.nodes.record_output(run.id, "draft_td", summary="drafted")

    await engine.nodes.say(run.id, "draft_td", text="section 3 is still wrong")

    reopened = await engine.attempts.latest_attempt(run.id, "draft_td")
    assert reopened.attempt == 2
    assert reopened.status == NodeStatus.PENDING.value
    assert reopened.instructions == "section 3 is still wrong"
    # The completed attempt keeps its own result and its own conversation.
    first = (await engine.attempts.list_attempts(run.id))[0]
    assert first.status == NodeStatus.COMPLETED.value
    assert first.summary == "drafted"


async def test_reopening_by_talking_stops_at_the_same_ceiling() -> None:
    """Spec workflow "Bound each task's attempts by its own ceiling": one
    ceiling, however the loop is spelled."""
    engine = build_engine({"delivery": with_ceiling(1)})
    run = await engine.started()
    engine.artifacts.add(run.id, "draft_td", 1, "td.md")
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    await engine.nodes.record_output(run.id, "draft_td", summary="drafted")

    with pytest.raises(AttemptCeilingReached) as caught:
        await engine.nodes.say(run.id, "draft_td", text="again please")
    assert caught.value.node_key == "draft_td"
    assert caught.value.ceiling == 1


async def test_a_task_whose_turn_is_in_flight_says_so(engine: Engine) -> None:
    """The agent owns a running task; the sentence belongs in its conversation."""
    run = await engine.started()
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)

    with pytest.raises(IllegalTransition) as caught:
        await engine.nodes.say(run.id, "draft_td", text="stop")
    assert "its turn" in caught.value.subject


async def test_nothing_said_is_refused_before_anything_is_written(engine: Engine) -> None:
    run = await engine.started()
    with pytest.raises(IllegalTransition):
        await engine.nodes.say(run.id, "write_code", text="   ")
    assert await engine.attempts.latest_attempt(run.id, "write_code") is None


async def test_a_manual_task_in_review_is_briefed_rather_than_told_an_agent() -> None:
    """A manual task has no agent and no turn: dispatching a follow-up into a
    conversation it never opened would fail on a null id, and the person doing
    the work is who the sentence is for anyway."""
    stages = [dict(stage) for stage in TEMPLATE["stages"]]
    stages[0] = {
        **stages[0],
        "nodes": [{**stages[0]["nodes"][0], "type": "manual", "artifacts": []}],
    }
    engine = build_engine({"delivery": with_template(stages=stages)})
    run = await engine.started()
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    # The driver reports a manual node ready the moment it starts; the fake
    # dispatcher records instead of reporting, so the report is made here.
    await engine.nodes.record_output(run.id, "draft_td", summary="done by hand")
    assert (await engine.attempts.latest_attempt(run.id, "draft_td")).status == (
        NodeStatus.WAITING_REVIEW.value
    )

    await engine.nodes.say(run.id, "draft_td", text="check the staging config too")

    row = await engine.attempts.latest_attempt(run.id, "draft_td")
    assert row.attempt == 1
    assert row.status == NodeStatus.WAITING_REVIEW.value, "a manual task was put back to running"
    assert row.instructions == "check the staging config too"
    assert engine.types(run.id)[-1] == "node.briefed"
