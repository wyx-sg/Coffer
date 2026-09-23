# backend/coffer/surfaces/http/settings_routes.py
"""/api/v1/settings — backend-persisted user settings.

One setting, and not a settings table — the state on disk IS the setting. The
credential master key's actual location wins (file presence; see
MasterKeyManager), and PUT relocates it and audits the move; the Fernet key
itself never changes, so stored ciphertext is untouched.

The daemon's port is deliberately NOT here. It is read before the database
exists and before this app is mounted, so the surface that changes it has to
keep working when the daemon cannot start at all — which a route served by that
daemon cannot. It lives in ~/.coffer/daemon-config.json, reachable through
`coffer daemon port show/set/clear` alone.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.credential_composition import get_master_key_manager
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.schemas import CredentialSettingsIn, CredentialSettingsOut

router = APIRouter(
    prefix="/api/v1/settings",
    tags=["settings"],
    dependencies=[Depends(require_token)],
)


@router.get("/credentials", response_model=CredentialSettingsOut)
async def get_credential_settings(
    manager: Any = Depends(get_master_key_manager),  # noqa: B008
) -> CredentialSettingsOut:
    """Report where the master key currently lives."""
    return CredentialSettingsOut(master_key_storage=manager.location)


@router.put("/credentials", response_model=CredentialSettingsOut)
async def put_credential_settings(
    body: CredentialSettingsIn,
    manager: Any = Depends(get_master_key_manager),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> CredentialSettingsOut:
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
    return CredentialSettingsOut(master_key_storage=manager.location)
