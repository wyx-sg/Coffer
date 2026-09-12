# backend/coffer/surfaces/http/settings_routes.py
"""/api/v1/settings — backend-persisted user settings.

Two settings, neither of them a settings table — in both cases the state on
disk IS the setting. The credential master key's actual location wins (file
presence; see MasterKeyManager), and PUT relocates it and audits the move; the
Fernet key itself never changes, so stored ciphertext is untouched. The daemon
port lives in ~/.coffer/daemon-config.json because it is read before the
database exists (spec mcp-gateway FR-028); PUT only writes the file, since a
running daemon owns its bound socket and cannot move without restarting.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.infrastructure.daemon import config as daemon_config
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.daemon_routes import get_port
from coffer.surfaces.http.dependencies import (
    get_actor,
    get_audit_service,
    get_master_key_manager,
)
from coffer.surfaces.http.schemas import (
    CredentialSettingsIn,
    CredentialSettingsOut,
    DaemonPortSettingsIn,
    DaemonPortSettingsOut,
)

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


def _daemon_port_settings() -> DaemonPortSettingsOut:
    """Read the persisted setting back rather than echoing what was written.

    The file is the single source of truth for the *next* start, and the bound
    socket for this one; reporting both is what lets a client tell the user a
    restart is still owed.
    """
    configured = daemon_config.read_fixed_port()
    effective = get_port()
    return DaemonPortSettingsOut(
        configured_port=configured,
        effective_port=effective,
        restart_required=configured is not None and configured != effective,
    )


@router.get("/daemon", response_model=DaemonPortSettingsOut)
async def get_daemon_settings() -> DaemonPortSettingsOut:
    """Report the fixed port, if any, and the port this daemon is serving on."""
    return _daemon_port_settings()


@router.put("/daemon", response_model=DaemonPortSettingsOut)
async def put_daemon_settings(
    body: DaemonPortSettingsIn,
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> DaemonPortSettingsOut:
    """Fix the daemon's port, or clear it with ``null``. Idempotent; audited on change.

    The new port takes effect at the next daemon start, so the response still
    reports the port this process is bound to, with `restart_required` set.
    Bounds live in the config module (InvalidPort), not here — duplicating them
    at the surface is how the two drift apart.
    """
    current = daemon_config.read_fixed_port()
    if body.port == current:
        return _daemon_port_settings()
    try:
        daemon_config.write_fixed_port(body.port)
    except daemon_config.InvalidPort as exc:
        # write_fixed_port validates before it touches the file, so a rejected
        # port leaves the previous setting intact.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await audit.record(
        AuditEventType.DAEMON_PORT_SET.value,
        actor=actor,
        details={"port": body.port},
    )
    return _daemon_port_settings()
