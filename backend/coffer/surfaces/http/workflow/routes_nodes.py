"""``/api/v1/workflow/runs/{run_id}/nodes`` and ``…/tasks`` — one node at a time.

Three routes: the six node actions (FR-021), the ad-hoc task that joins a stage
with instructions of the developer's own (FR-028), and the feedback edge that
sends work back to an earlier stage by adding a task there (FR-025).

Neither route decides anything. Which actions are legal, what an action leaves
behind, whether a required artifact may be waived and where the ceiling is are
all ``WorkflowNodeService``'s answers; this module translates a body into that
call and a row back onto the wire.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from coffer.application.workflow.node_service import WorkflowNodeService
from coffer.application.workflow.ports import AttemptRepoPort
from coffer.application.workflow.run_service import WorkflowRunService
from coffer.domain.workflow.errors import IllegalTransition
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.workflow.converters import (
    attempt_out,
    event_actor,
    run_out,
)
from coffer.surfaces.http.workflow.dependencies import (
    get_workflow_attempt_repo,
    get_workflow_node_service,
    get_workflow_run_service,
)
from coffer.surfaces.http.workflow.schemas import (
    AdhocTaskIn,
    NodeActionIn,
    NodeAttemptOut,
    SendBackIn,
    SendBackOut,
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
        # by the token budget pauses the run instead (FR-018). There is no
        # attempt to answer with, and the run's new status is the answer.
        raise IllegalTransition(f"run {run_id}", result.run.status, f"node.{body.action.value}", ())
    return attempt_out(row)


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


@router.post("/runs/{run_id}/send-back", response_model=SendBackOut)
async def send_back(
    run_id: str,
    body: SendBackIn,
    nodes: WorkflowNodeService = Depends(get_workflow_node_service),  # noqa: B008
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> SendBackOut:
    """Send work back to an earlier stage along a feedback edge (FR-025).

    What lands there is a new task carrying ``note`` as its brief. The node
    that already passed in that stage is not reopened, retried or rewound —
    it answered a different question, and it keeps its answer.

    The one case with no task in the answer is the ceiling (FR-026): an edge
    that has already fired as many times as the template allows fails the run
    instead of sending work back again. That is an outcome, not a refusal, so
    it comes back as this run with ``task`` null rather than as an error.
    """
    result = await nodes.take_feedback(
        run_id,
        from_stage=body.from_stage,
        reason=body.reason,
        note=body.note,
        version=body.version,
        actor=event_actor(actor),
    )
    return SendBackOut(
        run=run_out(result.run, owned_here=runs.owned_here(result.run)),
        task=None if result.attempt is None else attempt_out(result.attempt),
    )
