"""``/api/v1/workflow/approvals`` — what is waiting for a decision (FR-044).

Two routes: everything pending across every run, and the one decision.

The decision route adds nothing to ``ApprovalService.decide`` except the two
answers HTTP has to give that a service call does not: ``404`` for an approval
that is not there (the service says ``None``), and ``409`` for one that has
expired — the held call it was guarding has already been failed, so the click
did not land and rendering it as though it had would be a lie (FR-037).

Every other repeat is a plain ``200`` with the terminal row, which is exactly
what idempotence means here: the same state comes back and nothing executes a
second time (FR-038).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from coffer.application.workflow.approval_service import ApprovalService
from coffer.application.workflow.ports import ApprovalRow
from coffer.application.workflow.run_service import WorkflowRunService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.workflow.errors import IllegalTransition
from coffer.domain.workflow.run import ApprovalStatus
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.workflow.converters import (
    approval_out,
)
from coffer.surfaces.http.workflow.dependencies import (
    get_workflow_approval_service,
    get_workflow_run_service,
)
from coffer.surfaces.http.workflow.schemas import (
    ApprovalDecisionIn,
    ApprovalListOut,
    ApprovalOut,
)

router = APIRouter(
    prefix="/api/v1/workflow",
    tags=["workflow"],
    dependencies=[Depends(require_token)],
)

#: An approval is not a Resource, so there is no ``ApprovalNotFound``.
#: ``ResourceNotFound`` is reused for the same reason ``commands.KIND_RUN``
#: reuses it: every surface already answers 404 to it.
KIND_APPROVAL = "workflow_approval"


@router.get("/approvals", response_model=ApprovalListOut)
async def list_approvals(
    run_id: str | None = Query(default=None),
    decision_status: ApprovalStatus | None = Query(default=None, alias="status"),  # noqa: B008
    approvals: ApprovalService = Depends(get_workflow_approval_service),  # noqa: B008
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
) -> ApprovalListOut:
    """Approvals across every run, pending first.

    Without ``run_id`` this walks the runs, because an approval belongs to one
    and the repository is keyed that way. Pending first because that is the
    only part of this list anyone can act on; within each half the order is the
    repository's own — oldest first, the order they were asked in.
    """
    rows: list[ApprovalRow] = []
    if run_id is not None:
        rows.extend(await approvals.list_for_run(run_id, status=decision_status))
    else:
        for run in await runs.list_runs():
            rows.extend(await approvals.list_for_run(run.id, status=decision_status))
    pending = [row for row in rows if row.status == ApprovalStatus.PENDING.value]
    decided = [row for row in rows if row.status != ApprovalStatus.PENDING.value]
    return ApprovalListOut(items=[approval_out(row) for row in pending + decided])


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalOut)
async def decide_approval(
    approval_id: str,
    body: ApprovalDecisionIn,
    approvals: ApprovalService = Depends(get_workflow_approval_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ApprovalOut:
    """Approve or reject one approval."""
    row = await approvals.decide(
        approval_id,
        decision=ApprovalStatus(body.decision),
        decided_by=actor,
        decided_surface="api",
        comment=body.comment,
        remember_tool_class=body.remember_tool_class,
    )
    if row is None:
        raise ResourceNotFound.named(KIND_APPROVAL, approval_id)
    if row.status == ApprovalStatus.EXPIRED.value:
        raise IllegalTransition(
            f"approval {approval_id}",
            row.status,
            body.decision,
            (),
        )
    return approval_out(row)
