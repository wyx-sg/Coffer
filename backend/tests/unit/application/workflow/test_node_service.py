"""``WorkflowNodeService``: the six actions, the reports, and what they refuse.

The whole of a run's behaviour is here — start, review, complete, advance, fail,
retry, skip, restore, budget — with no agent behind it, because the dispatcher
is a recorder. That is the point of the seam: if this file can prove the state
machine, the driver only has to prove that a turn happens.
"""

from __future__ import annotations

import pytest

from coffer.application.workflow.node_service import MissingRequiredArtifact
from coffer.domain.workflow.errors import (
    AttemptCeilingReached,
    IllegalTransition,
    NotThisMachine,
    RunTerminal,
    WorkflowVersionConflict,
)
from coffer.domain.workflow.run import (
    FailureReason,
    NodeAction,
    NodeStatus,
    RunSignal,
    RunStatus,
)

from .conftest import TEMPLATE, Engine, build_engine, with_ceiling, with_template


async def _running_first_node(engine: Engine) -> tuple[str, int]:
    """A run whose first node is mid-turn — most tests start here."""
    run = await engine.started()
    result = await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    return run.id, result.run.version


async def test_start_opens_an_attempt_and_dispatches_it(engine: Engine) -> None:
    """FR-019: a node's work is one conversation, in the run's directory."""
    run = await engine.started()

    result = await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)

    assert result.run.current_node_key == "draft_td"
    assert result.run.current_stage_key == "design"
    assert result.attempt is not None
    assert result.attempt.status == NodeStatus.RUNNING.value
    assert engine.types(run.id)[-1] == "node.started"
    dispatched = engine.dispatcher.last
    assert dispatched.node.key == "draft_td"
    # FR-053: the workdir is the one Coffer made for this run, not one
    # anybody was asked for.
    assert dispatched.workdir == f"/fake/workflows/{run.id}/workspace"
    assert dispatched.agent_key == "claude_code"
    assert dispatched.follow_up is None


async def test_start_is_refused_while_the_run_is_not_running(engine: Engine) -> None:
    run = await engine.create()

    with pytest.raises(IllegalTransition):
        await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)


async def test_only_one_node_runs_at_a_time(engine: Engine) -> None:
    """FR-017: the run has one node in flight, never two."""
    run_id, version = await _running_first_node(engine)

    with pytest.raises(IllegalTransition) as caught:
        await engine.nodes.act(run_id, "write_code", NodeAction.START, version=version)

    assert "draft_td is running" in str(caught.value)


async def test_a_stale_version_refuses_a_node_action(engine: Engine) -> None:
    run = await engine.started()

    with pytest.raises(WorkflowVersionConflict):
        await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version - 1)


async def test_a_node_action_on_another_machine_is_refused(engine: Engine) -> None:
    run = await engine.started()
    engine.machine.machine_id = "machine-b"

    with pytest.raises(NotThisMachine):
        await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)


async def test_a_node_action_on_a_terminal_run_is_refused(engine: Engine) -> None:
    run = await engine.started()
    aborted = await engine.runs.signal(run.id, RunSignal.ABORT, version=run.version)

    with pytest.raises(RunTerminal):
        await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=aborted.run.version)


async def test_an_unknown_node_key_is_refused_naming_the_real_ones(engine: Engine) -> None:
    run = await engine.started()

    with pytest.raises(IllegalTransition) as caught:
        await engine.nodes.act(run.id, "nope", NodeAction.START, version=run.version)

    assert caught.value.allowed == ("draft_td", "write_code")


@pytest.mark.acceptance(
    spec="workflow", scenario="a required artifact that was never written blocks completion"
)
async def test_output_without_the_required_artifact_waits_for_the_developer(
    engine: Engine,
) -> None:
    """FR-023: a node owing a file it never wrote does not complete itself."""
    run_id, _version = await _running_first_node(engine)

    result = await engine.nodes.record_output(run_id, "draft_td", summary="drafted", tokens=120)

    assert result.attempt is not None
    assert result.attempt.status == NodeStatus.WAITING_REVIEW.value
    assert engine.types(run_id)[-1] == "node.output_ready"
    assert result.run.tokens_spent == 120


async def test_output_with_its_artifact_completes_and_moves_the_run_on(
    engine: Engine,
) -> None:
    """FR-017: no command between one node finishing and the next being free."""
    run_id, _version = await _running_first_node(engine)
    engine.artifacts.add(run_id, "draft_td", 1, "td.md")

    result = await engine.nodes.record_output(run_id, "draft_td", summary="drafted")

    assert result.attempt is not None
    assert result.attempt.status == NodeStatus.COMPLETED.value
    assert engine.types(run_id)[-2:] == ["node.output_ready", "node.completed"]
    position = await engine.nodes.next_position(run_id)
    assert position is not None
    assert position.node_key == "write_code"


@pytest.mark.acceptance(
    spec="workflow", scenario="a required artifact that was never written blocks completion"
)
async def test_complete_refuses_a_missing_required_artifact_and_waiving_allows_it(
    engine: Engine,
) -> None:
    run_id, version = await _running_first_node(engine)
    result = await engine.nodes.record_output(run_id, "draft_td", summary="drafted")
    version = result.run.version

    with pytest.raises(MissingRequiredArtifact) as caught:
        await engine.nodes.act(run_id, "draft_td", NodeAction.COMPLETE, version=version)
    assert caught.value.missing == ("td.md",)

    waived = await engine.nodes.act(
        run_id, "draft_td", NodeAction.COMPLETE, version=version, waive_artifacts=True
    )
    assert waived.attempt is not None
    assert waived.attempt.status == NodeStatus.COMPLETED.value


async def test_feedback_reopens_the_same_attempt_rather_than_a_new_one(
    engine: Engine,
) -> None:
    """FR-021: feedback is more to do, not another try."""
    run_id, _version = await _running_first_node(engine)
    result = await engine.nodes.record_output(run_id, "draft_td", summary="drafted")

    fed = await engine.nodes.act(
        run_id,
        "draft_td",
        NodeAction.FEEDBACK,
        version=result.run.version,
        feedback="ground it in the repo",
    )

    assert fed.attempt is not None
    assert fed.attempt.attempt == 1
    assert fed.attempt.status == NodeStatus.RUNNING.value
    assert engine.dispatcher.last.follow_up == "ground it in the repo"
    assert engine.types(run_id)[-1] == "node.feedback_submitted"


async def test_empty_feedback_is_refused(engine: Engine) -> None:
    run_id, _version = await _running_first_node(engine)
    result = await engine.nodes.record_output(run_id, "draft_td", summary="drafted")

    with pytest.raises(IllegalTransition):
        await engine.nodes.act(
            run_id, "draft_td", NodeAction.FEEDBACK, version=result.run.version, feedback="  "
        )


async def test_retry_inserts_a_new_attempt_and_leaves_the_old_one_alone(
    engine: Engine,
) -> None:
    """FR-022: the earlier attempt keeps its conversation and its output."""
    run_id, _version = await _running_first_node(engine)
    first = (await engine.attempts.latest_attempt(run_id, "draft_td")).id
    await engine.attempts.update_attempt(first, conversation_id="conv-node")
    failed = await engine.nodes.record_failure(run_id, "draft_td", detail="boom")

    # on_failure defaults to `stop` for this node, so the run failed and the
    # developer is the one who retries.
    retried = await engine.nodes.act(
        run_id, "draft_td", NodeAction.RETRY, version=failed.run.version
    )

    assert retried.attempt is not None
    assert retried.attempt.attempt == 2
    old = engine.attempts.rows[first]
    assert old.status == NodeStatus.FAILED.value
    assert old.conversation_id == "conv-node"
    assert engine.types(run_id)[-1] == "node.retried"


async def test_a_failing_node_that_says_stop_fails_the_run(engine: Engine) -> None:
    """FR-024: the node's declared behaviour decides, not the engine."""
    run_id, _version = await _running_first_node(engine)

    result = await engine.nodes.record_failure(run_id, "draft_td", detail="agent died")

    assert result.run.status == RunStatus.FAILED.value
    assert engine.types(run_id)[-2:] == ["node.failed", "run.failed"]
    assert engine.audit.types()[-1] == "workflow_run_finished"


async def test_a_failing_node_that_says_retry_opens_the_next_attempt_itself(
    engine: Engine,
) -> None:
    run = await engine.started()
    engine.artifacts.add(run.id, "draft_td", 1, "td.md")
    started = await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    await engine.nodes.record_output(run.id, "draft_td", summary="drafted")
    position = await engine.nodes.next_position(run.id)
    assert position is not None
    current = await engine.run_repo.get_run(run.id)
    await engine.nodes.act(run.id, "write_code", NodeAction.START, version=current.version)
    del started

    result = await engine.nodes.record_failure(run.id, "write_code", detail="tests red")

    # `write_code` declares retry x1, so the engine opens attempt 2 rather than
    # failing the run.
    assert result.run.status == RunStatus.RUNNING.value
    assert (await engine.attempts.latest_attempt(run.id, "write_code")).attempt == 2
    assert engine.types(run.id)[-2:] == ["node.failed", "node.retried"]


async def test_a_failing_node_that_says_continue_lets_the_run_finish(engine: Engine) -> None:
    engine = build_engine(
        {
            "delivery": with_template(
                stages=[
                    {
                        "key": "only",
                        "name": "Only",
                        "nodes": [
                            {
                                "key": "flaky",
                                "name": "Flaky",
                                "type": "ai",
                                "on_failure": {"action": "continue"},
                            }
                        ],
                    }
                ],
                edges=[],
            )
        }
    )
    run = await engine.started()
    await engine.nodes.act(run.id, "flaky", NodeAction.START, version=run.version)

    result = await engine.nodes.record_failure(run.id, "flaky", detail="never mind")

    assert result.run.status == RunStatus.COMPLETED.value
    assert engine.types(run.id)[-2:] == ["node.failed", "run.completed"]


async def test_skip_settles_a_node_and_restore_opens_the_next_attempt(
    engine: Engine,
) -> None:
    run = await engine.started()

    skipped = await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    await engine.nodes.record_output(run.id, "draft_td", summary="drafted")
    current = await engine.run_repo.get_run(run.id)
    skipped = await engine.nodes.act(run.id, "draft_td", NodeAction.SKIP, version=current.version)
    assert skipped.attempt is not None
    assert skipped.attempt.status == NodeStatus.SKIPPED.value

    restored = await engine.nodes.act(
        run.id, "draft_td", NodeAction.RESTORE, version=skipped.run.version
    )

    assert restored.attempt is not None
    assert restored.attempt.attempt == 2
    assert restored.attempt.status == NodeStatus.PENDING.value
    # The skip is still in the log and on its own row — restoring reopens the
    # node, it does not erase what the developer did.
    assert "node.skipped" in engine.types(run.id)
    assert engine.types(run.id)[-1] == "node.restored"


@pytest.mark.acceptance(spec="workflow", scenario="a run reaches completed when its last node does")
async def test_the_last_node_completing_completes_the_run(engine: Engine) -> None:
    """FR-013: and the completed run refuses everything afterwards."""
    run = await engine.started()
    engine.artifacts.add(run.id, "draft_td", 1, "td.md")
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    await engine.nodes.record_output(run.id, "draft_td", summary="drafted")
    current = await engine.run_repo.get_run(run.id)
    await engine.nodes.act(run.id, "write_code", NodeAction.START, version=current.version)

    result = await engine.nodes.record_output(run.id, "write_code", summary="pushed")

    assert result.run.status == RunStatus.COMPLETED.value
    assert result.run.current_node_key is None
    assert engine.types(run.id)[-1] == "run.completed"
    with pytest.raises(RunTerminal):
        await engine.nodes.act(run.id, "write_code", NodeAction.RETRY, version=result.run.version)


async def test_a_manual_node_never_completes_itself(engine: Engine) -> None:
    engine = build_engine(
        {
            "delivery": with_template(
                stages=[
                    {
                        "key": "release",
                        "name": "Release",
                        "nodes": [
                            {"key": "press_button", "name": "Press the button", "type": "manual"}
                        ],
                    }
                ],
                edges=[],
            )
        }
    )
    run = await engine.started()
    await engine.nodes.act(run.id, "press_button", NodeAction.START, version=run.version)

    result = await engine.nodes.record_output(run.id, "press_button", summary="over to you")

    assert result.attempt is not None
    assert result.attempt.status == NodeStatus.WAITING_REVIEW.value
    assert result.run.status == RunStatus.RUNNING.value


async def test_the_driver_s_attempt_keyed_reports_reach_the_same_commands(
    engine: Engine,
) -> None:
    run_id, _version = await _running_first_node(engine)
    attempt = await engine.attempts.latest_attempt(run_id, "draft_td")

    await engine.nodes.record_conversation(attempt.id, "conv-node")
    result = await engine.nodes.report_output(attempt.id, "drafted", 40)

    assert engine.attempts.rows[attempt.id].conversation_id == "conv-node"
    assert result.run.tokens_spent == 40
    assert engine.types(run_id)[-1] == "node.output_ready"


async def test_reporting_output_for_a_node_that_is_not_running_is_refused(
    engine: Engine,
) -> None:
    run = await engine.started()

    with pytest.raises(IllegalTransition):
        await engine.nodes.record_output(run.id, "draft_td", summary="from nowhere")


async def test_the_walk_reports_what_is_open_and_what_may_start(engine: Engine) -> None:
    run = await engine.started()

    walk = await engine.nodes.walk(run.id)
    assert walk.startable is not None
    assert walk.startable.node_key == "draft_td"
    assert walk.unfinished == ("draft_td", "write_code")

    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    busy = await engine.nodes.walk(run.id)
    assert busy.startable is None
    assert busy.occupied_by == "draft_td"


@pytest.mark.acceptance(spec="workflow", scenario="editing a template leaves a running run alone")
async def test_the_template_is_read_from_the_snapshot_not_the_resource(
    engine: Engine,
) -> None:
    """FR-010 again, from the node side: a run keeps running its own copy."""
    run = await engine.started()
    engine.templates.configs["delivery"] = {"stages": []}

    result = await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)

    assert result.attempt is not None
    assert TEMPLATE["stages"][0]["key"] == "design"


async def test_an_explicit_retry_stops_at_the_attempt_ceiling(engine: Engine) -> None:
    """FR-026: the ceiling is a wall, not a suggestion."""
    engine = build_engine({"delivery": with_ceiling(1)})
    run_id, _version = await _running_first_node(engine)
    failed = await engine.nodes.record_failure(run_id, "draft_td", detail="boom")

    with pytest.raises(AttemptCeilingReached):
        await engine.nodes.act(run_id, "draft_td", NodeAction.RETRY, version=failed.run.version)


@pytest.mark.acceptance(spec="workflow", scenario="an interrupted node is reported, not resumed")
async def test_an_interrupted_attempt_can_be_retried_into_a_new_one(
    engine: Engine,
) -> None:
    """FR-027 + FR-022: reported, then recoverable."""
    run_id, _version = await _running_first_node(engine)
    await engine.runs.rebuild_projection(run_id)
    current = await engine.run_repo.get_run(run_id)

    retried = await engine.nodes.act(run_id, "draft_td", NodeAction.RETRY, version=current.version)

    first = await engine.attempts.list_attempts(run_id)
    assert first[0].failure_reason == FailureReason.INTERRUPTED.value
    assert retried.attempt is not None
    assert retried.attempt.attempt == 2


async def test_a_start_refused_by_the_lock_leaves_the_node_startable(engine: Engine) -> None:
    """The advancer reads a run a moment before it acts on it, so any command
    the developer issues in between refuses its start (FR-015).

    What must not survive that refusal is a half-written node. Marking the
    attempt running before the commit left one: nothing may act on a running
    node, and the advancer never offers it again, so the run stopped on a node
    no one could move.
    """
    run = await engine.started()
    original = engine.run_repo.update_run_projection
    refused = {"once": False}

    async def refuse_once(*args: object, **kwargs: object):
        if not refused["once"]:
            refused["once"] = True
            return None  # somebody else moved the run in between
        return await original(*args, **kwargs)  # type: ignore[arg-type]

    engine.run_repo.update_run_projection = refuse_once  # type: ignore[method-assign]

    with pytest.raises(WorkflowVersionConflict):
        await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)

    engine.run_repo.update_run_projection = original  # type: ignore[method-assign]
    row = await engine.attempts.latest_attempt(run.id, "draft_td")
    assert row is None or row.status == NodeStatus.PENDING.value, "the node was wedged running"

    # And the next tick simply starts it, with no developer involved.
    current = await engine.run_repo.get_run(run.id)
    started = await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=current.version)
    assert started.attempt is not None
    assert started.attempt.status == NodeStatus.RUNNING.value


@pytest.mark.acceptance(spec="workflow", scenario="each task is given its own number of tries")
async def test_each_task_is_given_its_own_number_of_tries() -> None:
    """FR-026: the limit belongs to the task, so two tasks in one workflow can
    be allowed different numbers of them — the draft that is cheap to redo and
    the step that must not be repeated are not the same judgement."""
    ceilings = {"draft_td": 3, "write_code": 1}
    stages = [
        {
            **stage,
            "nodes": [
                {
                    **node,
                    "attempt_ceiling": ceilings[node["key"]],
                    # Both ask to be retried five times; each is capped by its
                    # OWN ceiling and by nothing else.
                    "on_failure": {"action": "retry", "times": 5},
                }
                for node in stage["nodes"]
            ],
        }
        for stage in TEMPLATE["stages"]
    ]
    engine = build_engine({"delivery": with_template(stages=stages)})
    run = await engine.started()

    # The generous one: its failure opens a second attempt.
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    failed = await engine.nodes.record_failure(run.id, "draft_td", detail="boom")
    assert failed.run.status == RunStatus.RUNNING.value
    second = await engine.attempts.latest_attempt(run.id, "draft_td")
    assert second is not None
    assert second.attempt == 2

    current = await engine.run_repo.get_run(run.id)
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=current.version)
    engine.artifacts.add(run.id, "draft_td", 2, "td.md")
    done = await engine.nodes.record_output(run.id, "draft_td", summary="drafted")

    # The strict one, in the same workflow: its first failure is its last.
    await engine.nodes.act(run.id, "write_code", NodeAction.START, version=done.run.version)
    stopped = await engine.nodes.record_failure(run.id, "write_code", detail="boom")
    assert stopped.run.status == RunStatus.FAILED.value
    assert engine.types(run.id)[-1] == "run.failed"
    assert await engine.attempts.latest_attempt(run.id, "write_code") is not None
    assert (await engine.attempts.latest_attempt(run.id, "write_code")).attempt == 1
