"""``/api/v1/workflow/runs/{run_id}/nodes`` and ``…/tasks`` — one node at a time.

Three routes: the six node actions (FR-021), one sentence to a task whatever
state it is in (FR-068), and the ad-hoc task that joins a stage with
instructions of the developer's own (FR-028).

There is no fourth that sends work back to an earlier stage. A finding is acted
on by retrying the task that was wrong or by adding one that fixes it (FR-025),
both of which are already here — the route that existed took a template's own
edge, and the template no longer draws one.

Neither route decides anything. Which actions are legal, what an action leaves
behind, whether a required artifact may be waived and where the ceiling is are
all ``WorkflowNodeService``'s answers; this module translates a body into that
call and a row back onto the wire.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from coffer.application.workflow.node_service import WorkflowNodeService
from coffer.application.workflow.ports import AttemptRepoPort
from coffer.domain.workflow.errors import IllegalTransition
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.workflow.converters import (
    attempt_out,
    event_actor,
)
from coffer.surfaces.http.workflow.dependencies import (
    get_workflow_attempt_repo,
    get_workflow_node_service,
)
from coffer.surfaces.http.workflow.schemas import (
    AdhocTaskIn,
    AssignmentIn,
    NodeActionIn,
    NodeAttemptOut,
    SayIn,
)

router = APIRouter(
    prefix="/api/v1/workflow",
    tags=["workflow"],
    dependencies=[Depends(require_token)],
)


@router.post("/runs/{run_id}/nodes/{node_key}/actions", response_model=NodeAttemptOut)
async def act_on_node(
    run_id: str,
    node_key: str,
    body: NodeActionIn,
    nodes: WorkflowNodeService = Depends(get_workflow_node_service),  # noqa: B008
    attempts: AttemptRepoPort = Depends(get_workflow_attempt_repo),  # noqa: B008
    actor: str = Depends(get_actor),
) -> NodeAttemptOut:
    """Start, give feedback on, complete, retry, skip or restore a node."""
    result = await nodes.act(
        run_id,
        node_key,
        body.action,
        version=body.version,
        feedback=body.feedback,
        waive_artifacts=body.waive_artifacts,
        actor=event_actor(actor),
    )
    row = await attempts.latest_attempt(run_id, node_key) or result.attempt
    if row is None:
        # The one accepted command that opens no attempt: a ``start`` refused
        # by the token budget pauses the run instead. There is no
        # attempt to answer with, and the run's new status is the answer.
        raise IllegalTransition(f"run {run_id}", result.run.status, f"node.{body.action.value}", ())
    return attempt_out(row)


@router.post("/runs/{run_id}/nodes/{node_key}/say", response_model=NodeAttemptOut)
async def say_to_node(
    run_id: str,
    node_key: str,
    body: SayIn,
    nodes: WorkflowNodeService = Depends(get_workflow_node_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> NodeAttemptOut:
    """Say something to one task, whenever (FR-068).

    What it means depends on where the task is, and the service decides: a task
    that has not started is briefed, one waiting for review carries on, one
    that finished opens its next attempt. A task whose turn is in flight is the
    agent's — that sentence goes to the conversation, not here.

    The answer is the attempt the sentence landed on, which is how a caller
    learns whether it was queued onto the same one or opened the next.
    """
    result = await nodes.say(run_id, node_key, text=body.text, actor=event_actor(actor))
    if result.attempt is None:  # pragma: no cover - every branch answers with an attempt
        raise IllegalTransition(f"run {run_id}", "say", node_key, ())
    return attempt_out(result.attempt)


@router.post("/runs/{run_id}/nodes/{node_key}/assignment", response_model=NodeAttemptOut)
async def assign_node(
    run_id: str,
    node_key: str,
    body: AssignmentIn,
    nodes: WorkflowNodeService = Depends(get_workflow_node_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> NodeAttemptOut:
    """Choose who runs this task, on what, before it runs (FR-071).

    Only before: once the turn is in flight the conversation owns these
    settings and the task's own pickers write them there. Recorded on the
    ATTEMPT, so a retry given a stronger model leaves the first attempt's row
    still saying what it actually ran on.

    No version: this decides nothing about where the run is.
    """
    result = await nodes.assign(
        run_id,
        node_key,
        agent=body.agent,
        model=body.model,
        effort=body.effort,
        actor=event_actor(actor),
    )
    if result.attempt is None:  # pragma: no cover - assign always answers with one
        raise IllegalTransition(f"run {run_id}", "assign", node_key, ())
    return attempt_out(result.attempt)


@router.post(
    "/runs/{run_id}/tasks",
    response_model=NodeAttemptOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_adhoc_task(
    run_id: str,
    body: AdhocTaskIn,
    nodes: WorkflowNodeService = Depends(get_workflow_node_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> NodeAttemptOut:
    """Add an unplanned task to a stage, with instructions of your own (FR-028).

    The task joins the run as a node keyed ``adhoc:<slug>``. The slug is minted
    inside the service — a name that repeats gets a numeric suffix rather than
    silently sharing another task's attempts — so the key comes back out of the
    log the command just wrote, which is where it was recorded.
    """
    result = await nodes.add_adhoc_task(
        run_id,
        stage_key=body.stage_key,
        name=body.name,
        instructions=body.instructions,
        version=body.version,
        agent=body.agent,
        workdir=body.workdir,
        actor=event_actor(actor),
    )
    if result.attempt is None:  # pragma: no cover - the command opens the attempt it answers with
        raise IllegalTransition(f"run {run_id}", "adhoc", body.stage_key, ())
    return attempt_out(result.attempt)
