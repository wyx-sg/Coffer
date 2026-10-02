"""The secret boundary's approval routes: list, read, approve, reject, ask again.

Spec secret "Hold a secret for a new destination until a person approves it".
Mounted on the secret boundary's router (``secret_boundary_routes``), whose
prefix and token check they share. Approving takes a presence grant the desktop
shell signs; refusing and asking again need none, because they only narrow or
re-ask.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.secret_boundary_wiring import (
    approval_applied,
    approval_out,
    get_presence_grants,
    get_secret_boundary,
    refresh_approvals,
)
from coffer.surfaces.http.secret_schemas import ApprovalListOut, ApprovalOut, PresenceGrantIn

router = APIRouter()


@router.get("/approvals", response_model=ApprovalListOut)
async def list_approvals(
    status: str | None = Query(default=None, pattern=r"^(pending|approved|rejected|superseded)$"),
    destination_uid: str | None = None,
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> ApprovalListOut:
    """Approvals, newest first — brought up to the configuration first, so a
    change saved a moment ago is already on the list."""
    for created in await refresh_approvals():
        await audit.record(
            AuditEventType.SECRET_APPROVAL_REQUESTED.value,
            actor=created.requested_by,
            details={"approval_id": created.id, "op": created.op, "ref": created.ref},
        )
    boundary = get_secret_boundary()
    rows = await asyncio.to_thread(
        lambda: boundary.list(status=status, destination_uid=destination_uid)
    )
    return ApprovalListOut(approvals=[approval_out(a) for a in rows])


@router.get("/approvals/{approval_id}", response_model=ApprovalOut)
async def get_approval(approval_id: str) -> ApprovalOut:
    boundary = get_secret_boundary()
    return approval_out(await asyncio.to_thread(boundary.get, approval_id))


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalOut)
async def approve(
    approval_id: str,
    grant: PresenceGrantIn,
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> ApprovalOut:
    """Apply a pending approval, against a presence grant for exactly this id."""
    boundary, grants = get_secret_boundary(), get_presence_grants()
    grants.redeem("approve", approval_id, grant.nonce, grant.signature)
    approved = await asyncio.to_thread(boundary.approve, approval_id, actor="desktop")
    approval_applied()
    await audit.record(
        AuditEventType.SECRET_APPROVAL_APPROVED.value,
        actor="desktop",
        details={"approval_id": approved.id, "op": approved.op, "ref": approved.ref},
    )
    return approval_out(approved)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalOut)
async def reject(
    approval_id: str,
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ApprovalOut:
    """Refuse a pending approval. Needs no presence: refusing only narrows."""
    boundary = get_secret_boundary()
    rejected = await asyncio.to_thread(boundary.reject, approval_id, actor=actor)
    await audit.record(
        AuditEventType.SECRET_APPROVAL_REJECTED.value,
        actor=actor,
        details={"approval_id": rejected.id, "op": rejected.op, "ref": rejected.ref},
    )
    return approval_out(rejected)


@router.post("/approvals/{approval_id}/ask-again", response_model=ApprovalListOut)
async def ask_again(
    approval_id: str,
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ApprovalListOut:
    """Lift a refusal so the same binding is put to a person again.

    Asking widens nothing: the new approval still waits for a presence grant.
    Answers what now waits for the refused binding's destination.
    """
    boundary = get_secret_boundary()
    refused = await asyncio.to_thread(boundary.get, approval_id)
    await asyncio.to_thread(boundary.ask_again, approval_id, actor=actor)
    for created in await refresh_approvals():
        await audit.record(
            AuditEventType.SECRET_APPROVAL_REQUESTED.value,
            actor=created.requested_by,
            details={"approval_id": created.id, "op": created.op, "ref": created.ref},
        )
    rows = await asyncio.to_thread(
        lambda: boundary.list(status="pending", destination_uid=refused.destination_uid)
    )
    return ApprovalListOut(approvals=[approval_out(a) for a in rows])
