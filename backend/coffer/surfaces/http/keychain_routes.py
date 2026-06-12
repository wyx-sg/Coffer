# backend/coffer/surfaces/http/keychain_routes.py
"""/api/v1/keychain — write secrets into the OS keychain.

The UI uses this when importing MCP server JSON: any plaintext secret in
the pasted `env` is lifted into the keychain here, so it never lands in
Coffer's database — the resource config only keeps a credential ref.

Every lifecycle change is audited (FR-014). The audit row records the
`ref` only — secret values never appear in the audit log.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service, get_keyring
from coffer.surfaces.http.schemas import (
    KeychainExistsOut,
    KeychainGetOut,
    KeychainSetIn,
)

router = APIRouter(
    prefix="/api/v1/keychain",
    tags=["keychain"],
    dependencies=[Depends(require_token)],
)


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def set_secret(
    body: KeychainSetIn,
    keyring: KeyringAdapter = Depends(get_keyring),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Store `value` under `ref` in the OS keychain."""
    keyring.set(body.ref, body.value)
    await audit.record(
        AuditEventType.KEYCHAIN_SET.value,
        actor=actor,
        details={"ref": body.ref},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{ref:path}/exists", response_model=KeychainExistsOut)
async def secret_exists(
    ref: str,
    keyring: KeyringAdapter = Depends(get_keyring),  # noqa: B008
) -> KeychainExistsOut:
    """Report whether a secret is stored under `ref`.

    Presence only — the value never crosses the API for this check, so no
    audit event is recorded (nothing sensitive is read out).
    """
    return KeychainExistsOut(present=keyring.get(ref) is not None)


@router.get("/{ref:path}", response_model=KeychainGetOut)
async def get_secret(
    ref: str,
    keyring: KeyringAdapter = Depends(get_keyring),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> KeychainGetOut:
    """Return the secret value stored under `ref`.

    Reading a value out is audited (ref only — the value never reaches the
    audit row), so explicit secret reads leave a trail. 404 when absent.
    """
    value = keyring.get(ref)
    if value is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await audit.record(
        AuditEventType.KEYCHAIN_READ.value,
        actor=actor,
        details={"ref": ref},
    )
    return KeychainGetOut(value=value)


@router.delete(
    "/{ref:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_secret(
    ref: str,
    keyring: KeyringAdapter = Depends(get_keyring),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Remove `ref` from the OS keychain. Idempotent — absent is fine."""
    keyring.delete(ref)
    await audit.record(
        AuditEventType.KEYCHAIN_DELETED.value,
        actor=actor,
        details={"ref": ref},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
