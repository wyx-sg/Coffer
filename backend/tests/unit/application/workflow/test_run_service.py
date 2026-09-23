"""``WorkflowRunService``: creation, the four signals, restart, deletion.

Each test names the FR it holds down, because the value of this file is not
that the code runs — it is that the refusals happen, and a refusal that quietly
stops happening looks exactly like a passing test unless something asserts it.
"""

from __future__ import annotations

import pytest

from coffer.domain.errors import ResourceNotFound
from coffer.domain.workflow.errors import (
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

from .conftest import TEMPLATE, Engine, build_engine


@pytest.mark.acceptance(
    spec="workflow", scenario="a task is its own conversation, opened from the run"
)
async def test_create_freezes_the_template_and_opens_no_conversation(engine: Engine) -> None:
    run = await engine.create()

    assert run.template_snapshot == TEMPLATE
    assert run.template_ref == "delivery"
    assert run.status == RunStatus.DRAFT.value
    assert run.version == 1
    assert run.machine_id == "machine-a"
    # A run has no conversation of its own. Creating one opens nothing
    # and spends nothing — every conversation belongs to a task, and the driver
    # opens it when that task starts.
    assert engine.turns.conversations == []
    assert engine.types(run.id) == ["run.created"]
    assert engine.artifacts.created == [run.id]


@pytest.mark.acceptance(spec="workflow", scenario="editing a template leaves a running run alone")
async def test_editing_the_template_does_not_reach_a_created_run(engine: Engine) -> None:
    """The snapshot is the run's, and the resource may move on."""
    run = await engine.create()

    engine.templates.configs["delivery"] = {
        "stages": [
            {"key": "other", "name": "Other", "nodes": [{"key": "x", "name": "X", "type": "ai"}]}
        ]
    }

    stored = await engine.latest(run.id)
    assert [s["key"] for s in stored.template_snapshot["stages"]] == ["design", "coding"]


async def test_create_refuses_an_unknown_template(engine: Engine) -> None:
    with pytest.raises(ResourceNotFound):
        await engine.create(template="nope")


@pytest.mark.acceptance(
    spec="workflow", scenario="a run is created from a template and a title alone"
)
async def test_create_asks_for_nothing_but_a_template_and_a_title(engine: Engine) -> None:
    """No working directory, no inputs."""
    run = await engine.create()

    # Coffer made the working directory, under the run's own tree, and created
    # it before recording the run that names it.
    assert run.workdir == f"/fake/workflows/{run.id}/workspace"
    assert engine.artifacts.created == [run.id]
    # A run starts reading nothing; inputs are mounted afterwards.
    assert run.inputs == []


async def test_start_runs_the_run_and_audits_it(engine: Engine) -> None:
    run = await engine.create()

    result = await engine.runs.signal(run.id, RunSignal.START, version=run.version)

    assert result.run.status == RunStatus.RUNNING.value
    assert result.run.version == 2
    assert engine.types(run.id) == ["run.created", "run.started"]
    assert engine.audit.types() == ["workflow_run_started"]


async def test_pause_resume_and_abort_walk_the_state_machine(engine: Engine) -> None:
    run = await engine.started()

    paused = await engine.runs.signal(run.id, RunSignal.PAUSE, version=run.version)
    assert paused.run.status == RunStatus.PAUSED.value
    resumed = await engine.runs.signal(run.id, RunSignal.RESUME, version=paused.run.version)
    assert resumed.run.status == RunStatus.RUNNING.value
    aborted = await engine.runs.signal(
        run.id, RunSignal.ABORT, version=resumed.run.version, reason="changed my mind"
    )
    assert aborted.run.status == RunStatus.ABORTED.value
    assert engine.audit.types() == ["workflow_run_started", "workflow_run_finished"]


async def test_an_illegal_signal_says_what_is_allowed(engine: Engine) -> None:
    run = await engine.create()

    with pytest.raises(IllegalTransition) as caught:
        await engine.runs.signal(run.id, RunSignal.PAUSE, version=run.version)

    assert caught.value.allowed == ("abort", "start")


@pytest.mark.acceptance(spec="workflow", scenario="an aborted run refuses everything afterwards")
async def test_an_aborted_run_refuses_every_later_command(engine: Engine) -> None:
    """Each signal is taken in turn, and the abort is the end.

    "Never again" is a different answer from "not from here", and the refusal
    has to cover the commands that name a NODE as well as the ones that name
    the run: a node action is the path an aborted run is most likely to be
    moved down by mistake, because the developer is looking at a task rather
    than at the run's status. What the last assertion holds is "refused rather
    than applied" — a refusal that had already written its event would leave
    the run's log saying something happened after the abort.
    """
    run = await engine.started()
    paused = await engine.runs.signal(run.id, RunSignal.PAUSE, version=run.version)
    assert paused.run.status == RunStatus.PAUSED.value
    resumed = await engine.runs.signal(run.id, RunSignal.RESUME, version=paused.run.version)
    assert resumed.run.status == RunStatus.RUNNING.value
    aborted = await engine.runs.signal(run.id, RunSignal.ABORT, version=resumed.run.version)
    assert aborted.run.status == RunStatus.ABORTED.value

    version = aborted.run.version
    settled = engine.types(run.id)

    with pytest.raises(RunTerminal):
        await engine.runs.signal(run.id, RunSignal.RESUME, version=version)
    with pytest.raises(RunTerminal):
        await engine.nodes.act(run.id, "draft_td", NodeAction.START, version=version)
    with pytest.raises(RunTerminal):
        await engine.nodes.add_adhoc_task(
            run.id, stage_key="design", name="One more", instructions="x", version=version
        )
    with pytest.raises(RunTerminal):
        await engine.nodes.say(run.id, "draft_td", text="carry on")

    # Nothing was applied: same version, same log, same status.
    after = await engine.latest(run.id)
    assert (after.version, after.status) == (version, RunStatus.ABORTED.value)
    assert engine.types(run.id) == settled


async def test_abort_supersedes_the_approvals_waiting_on_the_developer(engine: Engine) -> None:
    run = await engine.started()
    await engine.approvals.create_approval(
        approval_id="ap-1",
        run_id=run.id,
        kind="tool_call",
        payload={"project": "COF"},
        expires_at=run.created_at,
    )

    result = await engine.runs.signal(run.id, RunSignal.ABORT, version=run.version)

    assert (await engine.approvals.get_approval("ap-1")).status == "superseded"
    assert result.run.status == RunStatus.ABORTED.value


async def test_a_stale_version_is_refused_with_the_run_s_position(engine: Engine) -> None:
    """Two clients, one observed version, one change."""
    run = await engine.started()
    stale = run.version - 1

    with pytest.raises(WorkflowVersionConflict) as caught:
        await engine.runs.signal(run.id, RunSignal.PAUSE, version=stale)

    assert caught.value.expected == stale
    assert caught.value.current == run.version
    assert caught.value.status == RunStatus.RUNNING.value
    # The run did not move.
    assert (await engine.latest(run.id)).status == RunStatus.RUNNING.value


@pytest.mark.acceptance(
    spec="workflow", scenario="a run is read-only on a machine that does not own it"
)
async def test_a_run_owned_elsewhere_is_read_only_here(engine: Engine) -> None:
    """Visible everywhere, advanced on one machine."""
    run = await engine.started()
    engine.machine.machine_id = "machine-b"

    with pytest.raises(NotThisMachine) as caught:
        await engine.runs.signal(run.id, RunSignal.PAUSE, version=run.version)

    assert caught.value.owner_machine_id == "machine-a"
    assert engine.runs.owned_here(run) is False


@pytest.mark.acceptance(spec="workflow", scenario="a run rebuilds itself from its events")
async def test_rebuild_restores_a_dropped_projection_from_the_events(engine: Engine) -> None:
    """The log is the truth; the projection is a cache of a fold."""
    run = await engine.started()
    row = engine.run_repo.rows[run.id]
    before = (row.status, row.current_stage_key, row.current_node_key, row.tokens_spent)
    row.status = RunStatus.DRAFT.value
    row.current_stage_key = "nonsense"
    row.tokens_spent = 999

    rebuilt = await engine.runs.rebuild_projection(run.id)

    assert (
        rebuilt.status,
        rebuilt.current_stage_key,
        rebuilt.current_node_key,
        rebuilt.tokens_spent,
    ) == before


@pytest.mark.acceptance(spec="workflow", scenario="an interrupted node is reported, not resumed")
async def test_rebuild_reports_an_interrupted_turn_and_keeps_its_conversation(
    engine: Engine,
) -> None:
    """Reported, not resumed and not dropped."""
    run = await engine.started()
    attempt = await engine.attempts.insert_attempt(
        attempt_id="att-1",
        run_id=run.id,
        stage_key="design",
        node_key="draft_td",
        attempt=1,
        status=NodeStatus.RUNNING.value,
        conversation_id="conv-node",
    )

    await engine.runs.rebuild_projection(run.id)

    stored = engine.attempts.rows[attempt.id]
    assert stored.status == NodeStatus.FAILED.value
    assert stored.failure_reason == FailureReason.INTERRUPTED.value
    assert stored.conversation_id == "conv-node"
    assert engine.types(run.id)[-1] == "node.failed"


async def test_rebuild_writes_nothing_when_the_projection_already_agrees(
    engine: Engine,
) -> None:
    """A version bump on every daemon start would stale every client's view."""
    run = await engine.started()

    rebuilt = await engine.runs.rebuild_projection(run.id)

    assert rebuilt.version == run.version


async def test_rebuild_all_skips_runs_this_machine_does_not_own(engine: Engine) -> None:
    mine = await engine.started()
    engine.run_repo.rows[mine.id].status = RunStatus.DRAFT.value
    theirs = build_engine(machine_id="machine-b")
    del theirs

    moved = await engine.runs.rebuild_all()

    assert moved == 1
    engine.machine.machine_id = "machine-b"
    assert await engine.runs.rebuild_all() == 0


async def test_delete_removes_the_run_and_its_directory(engine: Engine) -> None:
    run = await engine.create()

    await engine.runs.delete_run(run.id)

    assert run.id not in engine.run_repo.rows
    assert engine.artifacts.deleted == [run.id]
    with pytest.raises(ResourceNotFound):
        await engine.runs.get_run(run.id)


async def test_delete_is_refused_on_a_machine_that_does_not_own_the_run(
    engine: Engine,
) -> None:
    run = await engine.create()
    engine.machine.machine_id = "machine-b"

    with pytest.raises(NotThisMachine):
        await engine.runs.delete_run(run.id)
    assert run.id in engine.run_repo.rows
