"""The secret boundary's approval routes: list, read, approve, reject,
and approve or reject several at once.

Spec secret "Hold a secret for a new destination until a person approves it".
Mounted on the secret boundary's router (``secret_boundary_routes``), whose
prefix and token check they share. Approving takes a presence grant the desktop
shell signs; refusing needs none, because it only narrows. Approving several
takes ONE grant, signed over a digest of exactly the ``(id, fingerprint)`` pairs
the person was shown: an item whose target moved since, or that is no longer
pending, is skipped and reported, never approved.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query

from coffer.application.audit_service import AuditService
from coffer.application.secret.boundary import SecretBoundary
from coffer.domain.audit import AuditEventType
from coffer.domain.secret_errors import ApprovalNotFound, ApprovalNotPending
from coffer.domain.secrets import LOCAL_PROCESS_KIND, SecretApproval, batch_target
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.secret_boundary_wiring import (
    approval_applied,
    approval_out,
    get_presence_grants,
    get_secret_boundary,
    refresh_approvals,
)
from coffer.surfaces.http.secret_schemas import (
    ApprovalListOut,
    ApprovalOut,
    BatchApproveIn,
    BatchOut,
    BatchRejectIn,
    BatchResultOut,
    PresenceGrantIn,
)

router = APIRouter()
_log = logging.getLogger(__name__)


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


@router.post("/approvals/approve", response_model=BatchOut)
async def approve_batch(
    body: BatchApproveIn,
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> BatchOut:
    """Approve several pending approvals under one presence grant.

    The grant is for the digest of the listed ``(id, fingerprint)`` pairs, so
    the set approved is the set the person was shown. Each item is then applied
    only if it is still pending for that very target; the rest are skipped and
    named. Nothing outside the list is touched.
    """
    boundary, grants = get_secret_boundary(), get_presence_grants()
    grants.redeem(
        "approve_batch",
        batch_target((i.id, i.fingerprint) for i in body.items),
        body.nonce,
        body.signature,
    )
    # Bring the list up to the configuration, so a target that moved since the
    # person looked has already superseded its approval.
    for created in await refresh_approvals():
        await audit.record(
            AuditEventType.SECRET_APPROVAL_REQUESTED.value,
            actor=created.requested_by,
            details={"approval_id": created.id, "op": created.op, "ref": created.ref},
        )
    results: list[BatchResultOut] = []
    for item in body.items:
        results.append(await _approve_one(boundary, audit, item.id, item.fingerprint))
    if any(r.outcome == "approved" for r in results):
        approval_applied()
    return BatchOut(results=results)


async def _approve_one(
    boundary: SecretBoundary, audit: AuditService, approval_id: str, shown: str
) -> BatchResultOut:
    def skipped(reason: str, approval: SecretApproval | None = None) -> BatchResultOut:
        return BatchResultOut(
            id=approval_id,
            outcome="skipped",
            reason=reason,  # type: ignore[arg-type]
            approval=approval_out(approval) if approval else None,
        )

    try:
        current = await asyncio.to_thread(boundary.get, approval_id)
    except ApprovalNotFound:
        return skipped("not_found")
    if current.status != "pending":
        return skipped("not_pending", current)
    if current.op == "disable_protection" or current.destination_kind == LOCAL_PROCESS_KIND:
        # Weakening the protection, or handing a value to local programs an agent
        # can start, is never one of several: each takes its own prompt.
        return skipped("not_batchable", current)
    if (current.target_fingerprint or "") != shown:
        return skipped("changed", current)
    try:
        approved = await asyncio.to_thread(boundary.approve, approval_id, actor="desktop")
    except ApprovalNotPending:
        return skipped("not_pending")
    except Exception:
        _log.exception("batch approval %s could not be applied", approval_id)
        return skipped("failed", current)
    await audit.record(
        AuditEventType.SECRET_APPROVAL_APPROVED.value,
        actor="desktop",
        details={"approval_id": approved.id, "op": approved.op, "ref": approved.ref},
    )
    return BatchResultOut(id=approval_id, outcome="approved", approval=approval_out(approved))


@router.post("/approvals/reject", response_model=BatchOut)
async def reject_batch(
    body: BatchRejectIn,
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> BatchOut:
    """Refuse several pending approvals. Needs no presence: refusing only narrows."""
    boundary = get_secret_boundary()
    results: list[BatchResultOut] = []
    for approval_id in body.ids:
        try:
            rejected = await asyncio.to_thread(boundary.reject, approval_id, actor=actor)
        except ApprovalNotFound:
            results.append(BatchResultOut(id=approval_id, outcome="skipped", reason="not_found"))
            continue
        except ApprovalNotPending:
            results.append(BatchResultOut(id=approval_id, outcome="skipped", reason="not_pending"))
            continue
        await audit.record(
            AuditEventType.SECRET_APPROVAL_REJECTED.value,
            actor=actor,
            details={"approval_id": rejected.id, "op": rejected.op, "ref": rejected.ref},
        )
        results.append(
            BatchResultOut(id=approval_id, outcome="rejected", approval=approval_out(rejected))
        )
    return BatchOut(results=results)
