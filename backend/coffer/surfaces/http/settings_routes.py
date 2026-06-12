# backend/coffer/surfaces/http/settings_routes.py
"""/api/v1/settings — backend-persisted user settings.

Currently one setting: where the credential-store master key lives.
There is no settings table — the key's actual location IS the state
(file presence wins; see MasterKeyManager). PUT relocates the key and
audits the move; the Fernet key itself never changes, so stored
ciphertext is untouched by a relocation.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_actor,
    get_audit_service,
    get_master_key_manager,
)
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
    keychain write runs off the event loop (CODE-034 pattern).
    """
    if body.master_key_storage != manager.location:
        await asyncio.to_thread(manager.relocate, body.master_key_storage)
        await audit.record(
            AuditEventType.MASTER_KEY_RELOCATED.value,
            actor=actor,
            details={"to": body.master_key_storage},
        )
    return CredentialSettingsOut(master_key_storage=manager.location)
