"""``/api/v1/desktop`` — the command line's requests to the desktop shell.

Spec secret "Approve from the command line with the person's own presence
check" and desktop-app "Serve the command line's desktop requests"; design
align-cli-with-ui-and-add-tool-environments D8. The command line creates a
request and waits on it; the shell claims it (each claim is its heartbeat),
runs its own presence-checked flow and says how it ended. The daemon pins an
approval request to each approval's target as it stands when asked, so the
shell can refuse to sign for a target that moved.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from coffer.application.secret.desktop_requests import (
    DesktopRequest,
    DesktopRequests,
)
from coffer.domain.errors import ConfigValidationError
from coffer.domain.secret_errors import ApprovalNotPending, SecretNotFound
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.secret_boundary_wiring import get_secret_boundary, refresh_approvals
from coffer.surfaces.http.secret_composition import get_secret_store

router = APIRouter(
    prefix="/api/v1/desktop", tags=["desktop"], dependencies=[Depends(require_token)]
)

OpName = Literal[
    "approve",
    "reveal",
    "export_master_key",
    "import_master_key",
    "update_status",
    "update_check",
    "update_install",
    "update_auto_check",
    "uninstall",
]
StatusName = Literal["waiting", "claimed", "done", "cancelled", "failed", "expired"]

_requests = DesktopRequests()


def get_desktop_requests() -> DesktopRequests:
    return _requests


def reset_desktop_requests() -> None:
    """A fresh queue for a fresh daemon: no request, and no shell seen yet."""
    global _requests
    _requests = DesktopRequests()


class DesktopRequestIn(BaseModel):
    op: OpName
    #: ``approve``: the approvals to approve — exactly these, each still pending.
    approval_ids: list[str] = Field(default_factory=list, max_length=50)
    #: ``reveal``: the secret to show in the app.
    ref: str | None = None
    #: ``update_auto_check``: switch the daily update check on or off;
    #: ``uninstall``: open the dialog with Also delete my data ticked.
    enabled: bool | None = None


class PinnedApprovalOut(BaseModel):
    id: str
    #: The target the approval named when the request was made.
    fingerprint: str


class DesktopRequestOut(BaseModel):
    id: str
    op: OpName
    status: StatusName
    approvals: list[PinnedApprovalOut]
    ref: str | None
    enabled: bool | None = None
    #: How it ended, in the shell's words (``cancelled``, a failure's reason).
    message: str | None
    #: What the shell reported back (the updater's state); never a secret.
    result: dict[str, Any] | None = None
    #: Seconds until an unanswered request expires.
    expires_in_seconds: int


class DesktopFinishIn(BaseModel):
    status: Literal["done", "cancelled", "failed"]
    message: str | None = Field(default=None, max_length=500)
    result: dict[str, Any] | None = None


class DesktopStatusOut(BaseModel):
    #: Whether a desktop shell polled within the last few seconds.
    shell_running: bool
    #: Seconds since the shell last polled; ``null`` when it never has.
    last_seen_seconds: float | None


def _out(r: DesktopRequest, requests: DesktopRequests) -> DesktopRequestOut:
    remaining = max(0, int(r.expires_at - requests._clock()))
    return DesktopRequestOut(
        id=r.id,
        op=r.op,
        status=r.status,
        approvals=[PinnedApprovalOut(id=i, fingerprint=f) for i, f in r.approvals.items()],
        ref=r.ref,
        enabled=r.enabled,
        message=r.message,
        result=r.result,
        expires_in_seconds=remaining,
    )


_dep = Depends(get_desktop_requests)


@router.get("/status", response_model=DesktopStatusOut)
async def desktop_status(requests: DesktopRequests = _dep) -> DesktopStatusOut:
    """Whether the desktop app is running and serving requests."""
    return DesktopStatusOut(
        shell_running=requests.shell_running(), last_seen_seconds=requests.shell_last_seen()
    )


@router.post("/requests", response_model=DesktopRequestOut, status_code=201)
async def create_request(
    body: DesktopRequestIn, requests: DesktopRequests = _dep
) -> DesktopRequestOut:
    """Ask the desktop shell to do something only a present person may approve."""
    approvals: dict[str, str] = {}
    if body.op == "approve":
        if not body.approval_ids:
            raise ConfigValidationError("name the approvals to approve")
        # Up to the configuration first, so a target that moved has already
        # superseded its approval and is not offered to the person.
        await refresh_approvals()
        boundary = get_secret_boundary()
        for approval_id in dict.fromkeys(body.approval_ids):
            approval = await asyncio.to_thread(boundary.get, approval_id)
            if approval.status != "pending":
                raise ApprovalNotPending(approval_id, approval.status)
            approvals[approval_id] = approval.target_fingerprint or ""
    if body.op == "reveal":
        if not body.ref:
            raise ConfigValidationError("name the secret to reveal")
        if not await asyncio.to_thread(get_secret_store().exists, body.ref):
            raise SecretNotFound(body.ref)
    if body.op == "update_auto_check" and body.enabled is None:
        raise ConfigValidationError("say whether the update check is on or off")
    created = requests.create(body.op, approvals=approvals, ref=body.ref, enabled=body.enabled)
    return _out(created, requests)


@router.get("/requests/{request_id}", response_model=DesktopRequestOut)
async def get_request(request_id: str, requests: DesktopRequests = _dep) -> DesktopRequestOut:
    return _out(requests.get(request_id), requests)


@router.post("/requests/{request_id}/cancel", response_model=DesktopRequestOut)
async def cancel_request(request_id: str, requests: DesktopRequests = _dep) -> DesktopRequestOut:
    """Withdraw a request the shell has not shown yet."""
    return _out(requests.cancel(request_id), requests)


@router.post("/requests/claim", response_model=DesktopRequestOut, responses={204: {}})
async def claim_request(requests: DesktopRequests = _dep) -> DesktopRequestOut | Response:
    """The shell's poll: the next request to show, or 204 with nothing waiting."""
    claimed = requests.claim()
    if claimed is None:
        return Response(status_code=204)
    return _out(claimed, requests)


@router.post("/requests/{request_id}/finish", response_model=DesktopRequestOut)
async def finish_request(
    request_id: str, body: DesktopFinishIn, requests: DesktopRequests = _dep
) -> DesktopRequestOut:
    """The shell says how a request ended. It approves nothing: an approval is
    applied only by the approve route, against a presence grant."""
    return _out(requests.finish(request_id, body.status, body.message, body.result), requests)


__all__ = ["get_desktop_requests", "reset_desktop_requests", "router"]
