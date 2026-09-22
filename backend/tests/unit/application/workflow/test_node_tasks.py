"""Unplanned work — the one command that reshapes a run while it is going.

A template declares the work that was foreseen. Everything else arrives as an
ad-hoc task (FR-028), and that includes acting on a finding from a later task:
there is no route back through the template (FR-025), so what the developer
does instead — retry the task that was wrong, or add one that fixes it — is
what this file proves. The regression it guards is the one a delivery engine
usually ships: a send-back that resets what already passed.
"""

from __future__ import annotations

import pytest

from coffer.domain.workflow.errors import IllegalTransition
from coffer.domain.workflow.run import NodeAction, NodeStatus, RunStatus

from .conftest import Engine


@pytest.mark.acceptance(
    spec="workflow", scenario="sending work back is the developer's hand, not the template's route"
)
async def test_acting_on_a_finding_leaves_every_task_that_ran_holding_its_result(
    engine: Engine,
) -> None:
    """FR-025/FR-021/FR-028: the coding task is done, the next task found a
    problem with it, and neither of the two things the developer may do about
    it touches what already passed.

    The engine used to offer a third thing — a route declared in the template
    that fired on a reason and sent the run backwards. It is gone, so the first
    assertion here is that the frozen template has no routes to offer at all:
    without it a route could come back and every test below would still pass
    while the run silently rewound.
    """
    run = await engine.started()
    engine.artifacts.add(run.id, "draft_td", 1, "td.md")
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    done = await engine.nodes.record_output(run.id, "draft_td", summary="drafted")
    first_attempt = await engine.attempts.latest_attempt(run.id, "draft_td")
    await engine.attempts.update_attempt(first_attempt.id, conversation_id="conv-draft")

    # The later task reports that the design is wrong.
    await engine.nodes.act(run.id, "write_code", NodeAction.START, version=done.run.version)
    found = await engine.nodes.record_output(run.id, "write_code", summary="the design is wrong")

    # There is no route to take: a template carries stages and nothing else.
    template = engine.templates.configs["delivery"]
    assert "edges" not in template

    # What the developer does instead, first half: add a task that fixes it.
    added = await engine.nodes.add_adhoc_task(
        run.id,
        stage_key="design",
        name="Design issue",
        instructions="the retry policy contradicts section 3",
        version=found.run.version,
    )
    task = await engine.attempts.latest_attempt(run.id, "adhoc:design-issue")
    assert task.stage_key == "design"
    assert task.status == NodeStatus.PENDING.value
    assert task.instructions == "the retry policy contradicts section 3"

    # Second half: retry the task that was wrong. It opens attempt 2.
    retried = await engine.nodes.act(
        run.id, "draft_td", NodeAction.RETRY, version=added.run.version
    )
    assert retried.attempt is not None
    assert retried.attempt.attempt == 2

    # And attempt 1 is exactly as it was — its result, its conversation and its
    # artifact all still attributed to it, which is the whole of FR-025.
    passed = engine.attempts.rows[first_attempt.id]
    assert passed.status == NodeStatus.COMPLETED.value
    assert passed.summary == "drafted"
    assert passed.conversation_id == "conv-draft"
    assert [(a.node_key, a.attempt, a.name) for a in engine.artifacts.list_artifacts(run.id)] == [
        ("draft_td", 1, "td.md")
    ]
    # The task that raised the finding kept its own attempt too.
    coding = await engine.attempts.latest_attempt(run.id, "write_code")
    assert coding.attempt == 1
    assert coding.summary == "the design is wrong"


async def test_the_walk_hands_back_the_added_task_then_returns_to_the_source(
    engine: Engine,
) -> None:
    """A fix added to an EARLIER stage runs before the task that asked for it,
    and when it is done the walk comes back to that task rather than running on
    past it — which is what makes an ad-hoc task a usable replacement for the
    route that was deleted (FR-025)."""
    run = await engine.started()
    engine.artifacts.add(run.id, "draft_td", 1, "td.md")
    await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=run.version)
    done = await engine.nodes.record_output(run.id, "draft_td", summary="drafted")
    await engine.nodes.act(run.id, "write_code", NodeAction.START, version=done.run.version)
    found = await engine.nodes.record_output(run.id, "write_code", summary="the design is wrong")

    added = await engine.nodes.add_adhoc_task(
        run.id,
        stage_key="design",
        name="Design issue",
        instructions="rewrite section 3",
        version=found.run.version,
    )
    position = await engine.nodes.next_position(run.id)
    assert position is not None
    assert position.node_key == "adhoc:design-issue"

    await engine.nodes.act(
        run.id, "adhoc:design-issue", NodeAction.START, version=added.run.version
    )
    engine.artifacts.add(run.id, "adhoc:design-issue", 1, "report.md")
    await engine.nodes.record_output(run.id, "adhoc:design-issue", summary="rewritten")

    # Back where the finding came from: `write_code` kept its attempt and its
    # review, so the run stops there for the developer rather than running on.
    walk = await engine.nodes.walk(run.id)
    assert walk.startable is None
    assert walk.occupied_by == "write_code"
    assert (await engine.run_repo.get_run(run.id)).status == RunStatus.RUNNING.value


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
    # `write_code` declares no artifacts, so it owes the default `report.md`
    # (FR-072) and would otherwise stop for the developer rather than complete.
    engine.artifacts.add(run.id, "write_code", 1, "report.md")

    result = await engine.nodes.record_output(run.id, "write_code", summary="pushed")

    assert result.run.status == RunStatus.RUNNING.value
    position = await engine.nodes.next_position(run.id)
    assert position is not None
    assert position.node_key == "adhoc:tell-the-team"
