"""``/api/v1/workflow/runs/{run_id}/nodes`` and ``…/tasks`` — one node at a time.

Two routes, both of which answer with the node's latest attempt: the six node
actions (FR-021) and the ad-hoc task that joins a stage with instructions of the
developer's own (FR-028).

Neither route decides anything. Which actions are legal, what an action leaves
behind, whether a required artifact may be waived and where the ceiling is are
all ``WorkflowNodeService``'s answers; this module translates a body into that
call and a row back onto the wire.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from coffer.application.workflow.node_service import WorkflowNodeService
from coffer.application.workflow.ports import AttemptRepoPort, AttemptRow, EventRepoPort
from coffer.domain.workflow.errors import IllegalTransition
from coffer.domain.workflow.events import EventType
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.workflow.converters import (
    attempt_out,
    event_actor,
)
from coffer.surfaces.http.workflow.dependencies import (
    get_workflow_attempt_repo,
    get_workflow_event_repo,
    get_workflow_node_service,
)
from coffer.surfaces.http.workflow.schemas import (
    AdhocTaskIn,
    NodeActionIn,
    NodeAttemptOut,
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
    attempts: AttemptRepoPort = Depends(get_workflow_attempt_repo),  # noqa: B008
    events: EventRepoPort = Depends(get_workflow_event_repo),  # noqa: B008
    actor: str = Depends(get_actor),
) -> NodeAttemptOut:
    """Add an unplanned task to a stage, with instructions of your own (FR-028).

    The task joins the run as a node keyed ``adhoc:<slug>``. The slug is minted
    inside the service — a name that repeats gets a numeric suffix rather than
    silently sharing another task's attempts — so the key comes back out of the
    log the command just wrote, which is where it was recorded.
    """
    await nodes.add_adhoc_task(
        run_id,
        stage_key=body.stage_key,
        name=body.name,
        instructions=body.instructions,
        version=body.version,
        agent=body.agent,
        workdir=body.workdir,
        actor=event_actor(actor),
    )
    row = await _first_attempt_of_new_task(events, attempts, run_id)
    if row is None:  # pragma: no cover - the command appends the event it reads
        raise IllegalTransition(f"run {run_id}", "adhoc", body.stage_key, ())
    return attempt_out(row)


async def _first_attempt_of_new_task(
    events: EventRepoPort,
    attempts: AttemptRepoPort,
    run_id: str,
) -> AttemptRow | None:
    """The attempt of the ad-hoc task added last — the one just added.

    Read from the event log rather than by diffing the attempt table around the
    command: the log is the run's record of truth, and its last
    ``node.adhoc_added`` is by definition the task this request created.
    """
    node_key: str | None = None
    for row in await events.list_events(run_id):
        if row.event_type == EventType.NODE_ADHOC_ADDED.value and row.node_key:
            node_key = row.node_key
    if node_key is None:
        return None
    return await attempts.latest_attempt(run_id, node_key)
