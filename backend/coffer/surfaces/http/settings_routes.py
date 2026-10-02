# backend/coffer/surfaces/http/settings_routes.py
"""/api/v1/settings — backend-persisted user settings.

Two settings. ``/settings/secret-boundary`` is the approval requirement of the
secret boundary, which only the desktop app can switch off. The other is not a
settings table — the state on disk IS the setting. The
secret master key's actual location wins (file presence; see
MasterKeyManager), and PUT relocates it and audits the move; the Fernet key
itself never changes, so stored ciphertext is untouched.

The daemon's port is deliberately NOT here. It is read before the database
exists and before this app is mounted, so the surface that changes it has to
keep working when the daemon cannot start at all — which a route served by that
daemon cannot. It lives in ~/.coffer/daemon-config.json, reachable through
`coffer config get/set/unset daemon.port` alone.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.schemas import SecretSettingsIn, SecretSettingsOut
from coffer.surfaces.http.secret_boundary_wiring import get_secret_boundary
from coffer.surfaces.http.secret_composition import get_master_key_manager
from coffer.surfaces.http.secret_schemas import (
    SecretBoundarySettingsIn,
    SecretBoundarySettingsOut,
)

router = APIRouter(
    prefix="/api/v1/settings",
    tags=["settings"],
    dependencies=[Depends(require_token)],
)


@router.get("/secrets", response_model=SecretSettingsOut)
async def get_secret_settings(
    manager: Any = Depends(get_master_key_manager),  # noqa: B008
) -> SecretSettingsOut:
    """Report where the master key currently lives."""
    return SecretSettingsOut(master_key_storage=manager.location)


@router.put("/secrets", response_model=SecretSettingsOut)
async def put_secret_settings(
    body: SecretSettingsIn,
    manager: Any = Depends(get_master_key_manager),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> SecretSettingsOut:
    """Relocate the master key. Idempotent; the move itself is audited.

    Moving to "keychain" may trigger one OS authorisation prompt — the
    keychain write runs off the event loop.
    """
    if body.master_key_storage != manager.location:
        await asyncio.to_thread(manager.relocate, body.master_key_storage)
        await audit.record(
            AuditEventType.MASTER_KEY_RELOCATED.value,
            actor=actor,
            details={"to": body.master_key_storage},
        )
    return SecretSettingsOut(master_key_storage=manager.location)


@router.get("/secret-boundary", response_model=SecretBoundarySettingsOut)
async def get_secret_boundary_settings() -> SecretBoundarySettingsOut:
    """Whether a secret waits for approval before it goes somewhere new."""
    boundary = get_secret_boundary()
    pending = await asyncio.to_thread(lambda: boundary.list(status="pending"))
    waiting = next((a.id for a in pending if a.op == "disable_protection"), None)
    return SecretBoundarySettingsOut(
        require_approval=await asyncio.to_thread(boundary.protections_on),
        pending_approval_id=waiting,
    )


@router.put(
    "/secret-boundary",
    response_model=SecretBoundarySettingsOut,
    responses={202: {"model": SecretBoundarySettingsOut, "description": "Waiting for approval"}},
)
async def put_secret_boundary_settings(
    body: SecretBoundarySettingsIn,
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Any:
    """Turn the approval requirement on (at once) or off (after approval).

    Switching it off widens where secrets may go, so it waits for the desktop
    app like any new destination (spec secret "Turn the protection off
    only through the desktop app"): the answer is 202 with the approval id.
    """
    boundary = get_secret_boundary()
    if body.require_approval:
        changed = await asyncio.to_thread(boundary.enable_protections)
        if changed:
            await audit.record(
                AuditEventType.SECRET_PROTECTION_ENABLED.value, actor=actor, details={}
            )
        return SecretBoundarySettingsOut(require_approval=True)
    if not await asyncio.to_thread(boundary.protections_on):
        return SecretBoundarySettingsOut(require_approval=False)
    approval = await asyncio.to_thread(boundary.request_disable, actor)
    await audit.record(
        AuditEventType.SECRET_APPROVAL_REQUESTED.value,
        actor=actor,
        details={"approval_id": approval.id, "op": approval.op},
    )
    return JSONResponse(
        status_code=202,
        content=SecretBoundarySettingsOut(
            require_approval=True, pending_approval_id=approval.id
        ).model_dump(),
    )
