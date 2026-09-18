"""``/api/v1/workflow/runs`` — a run's whole management plane (FR-044).

List, create, read, delete, signal, and read the log. What one NODE accepts is
in ``routes_nodes`` and what a run READS is in ``routes_inputs``; the split is
the services' own, and it is also where the file-size ceiling falls.

**A run has no conversation of its own** (FR-030). There is no route here for
saying something to the run, because there is nothing to say it in: every
conversation belongs to one task, and the developer speaks to a task through
the ordinary chat API on that task's ``conversation_id``. A run-level message
route existed briefly and is gone — it described a main thread this layer no
longer has.

``GET /runs/{run_id}`` is the one route worth reading the code of rather than
the summary. It assembles the run's stages and nodes, and each node's
``allowed_actions`` comes from
``domain.workflow.transitions.allowed_node_actions`` — the same table the
command path consults. Those buttons now live on the conversation page rather
than the run's own (FR-052), which changes where they are drawn and not what
they are: a value computed any other way is still a button that 409s.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, Depends, Query, Response, status

from coffer.application.workflow.commands import template_of
from coffer.application.workflow.node_walk import adhoc_keys_in, adhoc_node
from coffer.application.workflow.ports import (
    AttemptRepoPort,
    AttemptRow,
    EventRepoPort,
    RunRow,
)
from coffer.application.workflow.run_label_ops import KEEP as _KEEP
from coffer.application.workflow.run_service import WorkflowRunService
from coffer.domain.workflow.events import EventType
from coffer.domain.workflow.run import (
    TERMINAL_RUN_STATUSES,
    NodeAction,
    NodeStatus,
    RunStatus,
)
from coffer.domain.workflow.template import Node, WorkflowTemplate
from coffer.domain.workflow.transitions import allowed_node_actions
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.workflow.converters import (
    attempt_out,
    event_actor,
    event_out,
    inputs_out,
    run_out,
)
from coffer.surfaces.http.workflow.dependencies import (
    get_workflow_attempt_repo,
    get_workflow_event_repo,
    get_workflow_run_service,
)
from coffer.surfaces.http.workflow.schemas import (
    EventListOut,
    NodeOut,
    RunCreateIn,
    RunDetailOut,
    RunLabelIn,
    RunListOut,
    RunOut,
    RunSignalIn,
    SendBackEdgeOut,
    StageOut,
)

router = APIRouter(
    prefix="/api/v1/workflow",
    tags=["workflow"],
    dependencies=[Depends(require_token)],
)


def latest_attempts(rows: Sequence[AttemptRow]) -> dict[str, AttemptRow]:
    """The attempt that counts now for each node key — the highest-numbered one.

    The same rule ``application.workflow.commands.RunCommands.latest_attempts``
    applies, over the same port; it is not reachable from here because it is an
    instance method of the command cycle, which this surface has no business
    holding.
    """
    latest: dict[str, AttemptRow] = {}
    for row in rows:
        current = latest.get(row.node_key)
        if current is None or row.attempt >= current.attempt:
            latest[row.node_key] = row
    return latest


@router.get("/runs", response_model=RunListOut)
async def list_runs(
    status_filter: RunStatus | None = Query(default=None, alias="status"),  # noqa: B008
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
) -> RunListOut:
    """Every run on this vault, newest first."""
    rows = await runs.list_runs(status=None if status_filter is None else status_filter.value)
    return RunListOut(items=[run_out(row, owned_here=runs.owned_here(row)) for row in rows])


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def create_run(
    body: RunCreateIn,
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> RunOut:
    """Create a run from a template, freezing the template's snapshot (FR-010).

    A template and a title, and nothing else (FR-011). The working directory is
    Coffer's own, made per run (FR-053) and reported back on the run; the inputs
    are mounted afterwards, through the routes that can also unmount them
    (FR-050).
    """
    run = await runs.create_run(
        template_uid=body.template_uid,
        title=body.title,
        agent=body.agent,
        actor=event_actor(actor),
    )
    return run_out(run, owned_here=runs.owned_here(run))


@router.get("/runs/{run_id}", response_model=RunDetailOut)
async def get_run(
    run_id: str,
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
    attempts: AttemptRepoPort = Depends(get_workflow_attempt_repo),  # noqa: B008
    events: EventRepoPort = Depends(get_workflow_event_repo),  # noqa: B008
) -> RunDetailOut:
    """One run, with its stages, nodes and latest attempts."""
    run = await runs.get_run(run_id)
    template = template_of(run)
    latest = latest_attempts(await attempts.list_attempts(run_id))
    adhoc = await _adhoc_nodes(events, run_id)
    owned_here = runs.owned_here(run)
    stages = [
        StageOut(
            key=stage.key,
            name=stage.name,
            optional=stage.optional,
            nodes=[
                _node_out(node, latest.get(node.key), run=run, owned_here=owned_here, adhoc=False)
                for node in stage.nodes
            ]
            + [
                _node_out(adhoc[key], latest.get(key), run=run, owned_here=owned_here, adhoc=True)
                for key in adhoc_keys_in(latest, stage.key)
                if key in adhoc
            ],
        )
        for stage in template.stages
    ]
    return RunDetailOut(
        run=run_out(run, owned_here=owned_here),
        stages=stages,
        inputs=inputs_out(run.inputs),
        send_backs=[
            SendBackEdgeOut(
                from_stage=edge.from_stage,
                to_stage=edge.to_stage,
                to_stage_name=_stage_name(template, edge.to_stage),
                reason=edge.reason,
            )
            for edge in template.edges
        ],
    )


def _stage_name(template: WorkflowTemplate, stage_key: str) -> str:
    stage = template.stage(stage_key)
    return stage_key if stage is None else stage.name


@router.patch("/runs/{run_id}", response_model=RunOut)
async def relabel_run(
    run_id: str,
    body: RunLabelIn,
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
) -> RunOut:
    """Rewrite what this run is called and what it is for (FR-070).

    The ONE in-place edit of a run's row, and it touches nothing the event log
    owns. A run's status, its stage and its position are folded from its events
    and only the engine writes them (FR-014); the title is a label the
    developer typed before the first task had opened, when they knew least
    about the work. No ``version``: the optimistic lock guards the position,
    and this moves the run nowhere.
    """
    # An ABSENT description leaves what is stored alone; an explicit null
    # clears it. `--title` on its own must not erase the words someone wrote
    # about the delivery a week ago.
    run = await runs.relabel_run(
        run_id,
        title=body.title,
        description=body.description if "description" in body.model_fields_set else _KEEP,
    )
    return run_out(run, owned_here=runs.owned_here(run))


@router.delete(
    "/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_run(
    run_id: str,
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
) -> Response:
    """Delete a run, its events, attempts, approvals and directory.

    The node conversations are not deleted — they are ordinary conversations
    and belong to the chat layer's retention.
    """
    await runs.delete_run(run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/runs/{run_id}/signals", response_model=RunOut)
async def signal_run(
    run_id: str,
    body: RunSignalIn,
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> RunOut:
    """Start, pause, resume or abort a run (FR-016)."""
    result = await runs.signal(
        run_id,
        body.signal,
        version=body.version,
        reason=body.reason,
        actor=event_actor(actor),
    )
    return run_out(result.run, owned_here=runs.owned_here(result.run))


@router.get("/runs/{run_id}/events", response_model=EventListOut)
async def list_run_events(
    run_id: str,
    after_sequence: int | None = Query(default=None),
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
    events: EventRepoPort = Depends(get_workflow_event_repo),  # noqa: B008
) -> EventListOut:
    """A run's event log, in sequence — its record of truth (FR-014)."""
    await runs.get_run(run_id)  # 404 for a run that is not there
    rows = await events.list_events(run_id, after_sequence=after_sequence)
    return EventListOut(items=[event_out(row) for row in rows])


# ---------------------------------------------------------------------------
# Assembling a run's detail
# ---------------------------------------------------------------------------


async def _adhoc_nodes(events: EventRepoPort, run_id: str) -> dict[str, Node]:
    """The run's ad-hoc tasks, rebuilt from the events that added them.

    The event log is where a task was recorded, so it is where it is read from
    — exactly as ``node_ops.adhoc_node_of`` does it, and for the same reason:
    there is no second table holding a shadow copy to drift from it.
    """
    out: dict[str, Node] = {}
    for row in await events.list_events(run_id):
        if row.event_type == EventType.NODE_ADHOC_ADDED.value and row.node_key:
            out[row.node_key] = adhoc_node(row.node_key, row.payload or {})
    return out


def _node_out(
    node: Node,
    row: AttemptRow | None,
    *,
    run: RunRow,
    owned_here: bool,
    adhoc: bool,
) -> NodeOut:
    node_status = NodeStatus.PENDING if row is None else NodeStatus(row.status)
    return NodeOut(
        key=node.key,
        name=node.name,
        type=node.type.value,
        skill=node.skill,
        agent=node.agent,
        approval=node.approval.value,
        status=node_status.value,
        attempt=_tries(row),
        adhoc=adhoc,
        allowed_actions=_allowed_actions(node, node_status, run=run, owned_here=owned_here),
        conversation_id=None if row is None else row.conversation_id,
        latest=None if row is None else attempt_out(row),
    )


def _tries(row: AttemptRow | None) -> int:
    """How many times this node has been TRIED — not which row is open.

    An attempt row exists before its turn does: a retry opens the next one
    pending, and so does briefing a task that has not started (FR-068). Neither
    is a try, so neither is counted until the row is started. Without this, a
    task the developer wrote a brief for would claim to be on its first attempt
    while sitting beside an identical one claiming zero, for a reason the
    reader cannot see.
    """
    if row is None:
        return 0
    return row.attempt if row.started_at is not None else row.attempt - 1


def _allowed_actions(
    node: Node,
    node_status: NodeStatus,
    *,
    run: RunRow,
    owned_here: bool,
) -> list[str]:
    """What this node accepts right now, in the run it is part of.

    ``allowed_node_actions`` answers for the node alone. Two of the run's own
    guards then narrow it, and they are the two ``RunCommands.guard`` applies
    before any action is even looked at: a run this machine does not own accepts
    nothing (FR-012), and a completed or aborted one accepts nothing ever again
    (FR-013). A third narrowing is ``node.start``'s own precondition — the run
    must be ``running`` (``WorkflowNodeService._start``) — without which a draft
    run would offer a Start button that refuses itself.
    """
    if not owned_here or RunStatus(run.status) in TERMINAL_RUN_STATUSES:
        return []
    actions = allowed_node_actions(node_status, node.type)
    if RunStatus(run.status) is not RunStatus.RUNNING:
        actions = actions - {NodeAction.START}
    return sorted(action.value for action in actions)
