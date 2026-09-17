"""Feedback edges and ad-hoc tasks — the two commands that reshape a run.

The two questions worth proving here are the ones a delivery engine usually
gets wrong: a feedback edge must not reset what already passed (FR-025), and a
loop between two stages must end at the ceiling rather than run all night
(FR-026).
"""

from __future__ import annotations

import pytest

from coffer.domain.workflow.errors import IllegalTransition
from coffer.domain.workflow.run import NodeAction, NodeStatus, RunStatus

from .conftest import TEMPLATE, Engine, build_engine, with_template


def _reviewed_coding_template() -> dict:
    """The default template, with the coding node stopping for a review.

    A feedback edge is taken by the developer looking at what the later stage
    produced, so the realistic shape is a node sitting in ``waiting_review`` —
    not one that has already completed, which would have completed the run.
    """
    stages = [dict(stage) for stage in TEMPLATE["stages"]]
    stages[1] = {**stages[1], "nodes": [{**stages[1]["nodes"][0], "approval": "always"}]}
    return with_template(stages=stages)


async def _design_done_coding_in_review(engine: Engine) -> str:
    """Design completed once; coding has reported and awaits the developer."""
    run = await engine.started()
    engine.artifacts.add(run.id, "draft_td", 1, "td.md")
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    await engine.nodes.record_output(run.id, "draft_td", summary="drafted")
    current = await engine.run_repo.get_run(run.id)
    await engine.nodes.act(run.id, "write_code", NodeAction.START, version=current.version)
    await engine.nodes.record_output(run.id, "write_code", summary="the design is wrong")
    return run.id


@pytest.mark.acceptance(
    spec="workflow", scenario="a feedback edge opens a new attempt without resetting what passed"
)
async def test_a_feedback_edge_reopens_the_target_without_resetting_the_rest(
    engine: Engine,
) -> None:
    """FR-025: the nodes completed in between keep their results."""
    run = await engine.started()
    engine.artifacts.add(run.id, "draft_td", 1, "td.md")
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    completed = await engine.nodes.record_output(run.id, "draft_td", summary="drafted")

    result = await engine.nodes.take_feedback(
        run.id,
        from_stage="coding",
        reason="design_issue",
        version=completed.run.version,
    )

    reopened = await engine.attempts.latest_attempt(run.id, "draft_td")
    assert reopened.attempt == 2
    assert reopened.status == NodeStatus.PENDING.value
    # Attempt 1 is untouched: its status, summary and conversation survive.
    first = (await engine.attempts.list_attempts(run.id))[0]
    assert first.status == NodeStatus.COMPLETED.value
    assert first.summary == "drafted"
    assert engine.types(run.id)[-1] == "node.retried"
    assert result.run.current_node_key == "draft_td"


async def test_the_walk_hands_back_the_reopened_node_then_returns_to_the_source() -> None:
    """The reopened node runs first even though the source is still in review."""
    engine = build_engine({"delivery": _reviewed_coding_template()})
    run_id = await _design_done_coding_in_review(engine)
    current = await engine.run_repo.get_run(run_id)
    await engine.nodes.take_feedback(
        run_id, from_stage="coding", reason="design_issue", version=current.version
    )

    position = await engine.nodes.next_position(run_id)
    assert position is not None
    assert position.node_key == "draft_td"

    current = await engine.run_repo.get_run(run_id)
    await engine.nodes.act(run_id, "draft_td", NodeAction.START, version=current.version)
    engine.artifacts.add(run_id, "draft_td", 2, "td.md")
    await engine.nodes.record_output(run_id, "draft_td", summary="redrafted")

    # Back where the edge was taken from: `write_code` kept its attempt and its
    # review, so the run stops there for the developer rather than running on.
    walk = await engine.nodes.walk(run_id)
    assert walk.startable is None
    assert walk.occupied_by == "write_code"
    assert (await engine.run_repo.get_run(run_id)).status == RunStatus.RUNNING.value


async def test_an_unknown_reason_takes_no_edge() -> None:
    engine = build_engine({"delivery": _reviewed_coding_template()})
    run_id = await _design_done_coding_in_review(engine)
    current = await engine.run_repo.get_run(run_id)

    with pytest.raises(IllegalTransition) as caught:
        await engine.nodes.take_feedback(
            run_id, from_stage="coding", reason="typo", version=current.version
        )

    assert caught.value.allowed == ("design_issue->design",)


@pytest.mark.acceptance(
    spec="workflow", scenario="a loop between two stages stops at the attempt ceiling"
)
async def test_the_loop_stops_at_the_attempt_ceiling_by_failing_the_run() -> None:
    """FR-026: the next pass fails the run instead of opening another try."""
    engine = build_engine({"delivery": {**_reviewed_coding_template(), "attempt_ceiling": 1}})
    run_id = await _design_done_coding_in_review(engine)
    current = await engine.run_repo.get_run(run_id)

    result = await engine.nodes.take_feedback(
        run_id, from_stage="coding", reason="design_issue", version=current.version
    )

    assert result.run.status == RunStatus.FAILED.value
    assert engine.types(run_id)[-1] == "run.failed"
    # No second attempt was opened.
    assert (await engine.attempts.latest_attempt(run_id, "draft_td")).attempt == 1
    assert engine.audit.types()[-1] == "workflow_run_finished"


@pytest.mark.acceptance(
    spec="workflow", scenario="an ad-hoc task joins a stage and carries the same context"
)
async def test_an_adhoc_task_joins_a_stage_and_runs_like_any_node(engine: Engine) -> None:
    """FR-028: recorded, contextualised and attributed exactly as a node is."""
    run = await engine.started()

    added = await engine.nodes.add_adhoc_task(
        run.id,
        stage_key="design",
        name="Check the migration",
        instructions="Read 0085 and say whether it is reversible.",
        version=run.version,
    )

    assert engine.types(run.id)[-1] == "node.adhoc_added"
    attempt = await engine.attempts.latest_attempt(run.id, "adhoc:check-the-migration")
    assert attempt is not None
    assert attempt.stage_key == "design"
    assert attempt.instructions == "Read 0085 and say whether it is reversible."

    # It sits at the end of its stage: the stage's own plan was written first.
    walk = await engine.nodes.walk(run.id)
    assert walk.unfinished == ("draft_td", "adhoc:check-the-migration", "write_code")

    current = added.run
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=current.version)
    engine.artifacts.add(run.id, "draft_td", 1, "td.md")
    await engine.nodes.record_output(run.id, "draft_td", summary="drafted")

    position = await engine.nodes.next_position(run.id)
    assert position is not None
    assert position.node_key == "adhoc:check-the-migration"


@pytest.mark.acceptance(
    spec="workflow", scenario="an ad-hoc task joins a stage and carries the same context"
)
async def test_an_adhoc_task_dispatches_with_its_own_instructions_and_workdir(
    engine: Engine,
) -> None:
    run = await engine.started()
    added = await engine.nodes.add_adhoc_task(
        run.id,
        stage_key="design",
        name="Fix the other repo",
        instructions="Bump the client version.",
        version=run.version,
        agent="codex",
        workdir="/other-repo",
    )

    await engine.nodes.act(
        run.id, "adhoc:fix-the-other-repo", NodeAction.START, version=added.run.version
    )

    dispatched = engine.dispatcher.last
    assert dispatched.node.instructions == "Bump the client version."
    assert dispatched.agent_key == "codex"
    # A task pointed at a second repository is how that work is expressed
    # without leaving the run (spec, Assumptions).
    assert dispatched.workdir == "/other-repo"


async def test_two_tasks_with_the_same_name_get_different_keys(engine: Engine) -> None:
    run = await engine.started()
    first = await engine.nodes.add_adhoc_task(
        run.id, stage_key="design", name="Look again", instructions="once", version=run.version
    )
    second = await engine.nodes.add_adhoc_task(
        run.id,
        stage_key="design",
        name="Look again",
        instructions="twice",
        version=first.run.version,
    )

    keys = sorted(row.node_key for row in await engine.attempts.list_attempts(run.id))
    assert keys == ["adhoc:look-again", "adhoc:look-again-2"]
    assert second.run.version == first.run.version + 1


async def test_a_task_added_to_a_stage_that_does_not_exist_is_refused(
    engine: Engine,
) -> None:
    run = await engine.started()

    with pytest.raises(IllegalTransition) as caught:
        await engine.nodes.add_adhoc_task(
            run.id, stage_key="nope", name="x", instructions="y", version=run.version
        )

    assert caught.value.allowed == ("design", "coding")


async def test_a_pending_task_holds_the_run_open(engine: Engine) -> None:
    """A run with unplanned work still to do has not finished."""
    run = await engine.started()
    added = await engine.nodes.add_adhoc_task(
        run.id,
        stage_key="coding",
        name="Tell the team",
        instructions="post it",
        version=run.version,
    )
    engine.artifacts.add(run.id, "draft_td", 1, "td.md")
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=added.run.version)
    await engine.nodes.record_output(run.id, "draft_td", summary="drafted")
    current = await engine.run_repo.get_run(run.id)
    await engine.nodes.act(run.id, "write_code", NodeAction.START, version=current.version)

    result = await engine.nodes.record_output(run.id, "write_code", summary="pushed")

    assert result.run.status == RunStatus.RUNNING.value
    position = await engine.nodes.next_position(run.id)
    assert position is not None
    assert position.node_key == "adhoc:tell-the-team"
