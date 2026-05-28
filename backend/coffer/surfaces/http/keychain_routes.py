# backend/coffer/surfaces/http/keychain_routes.py
"""/api/v1/keychain — write secrets into the OS keychain.

The UI uses this when importing MCP server JSON: any plaintext secret in
the pasted `env` is lifted into the keychain here, so it never lands in
Coffer's database — the resource config only keeps a credential ref.

Every lifecycle change is audited (FR-014). The audit row records the
`ref` only — secret values never appear in the audit log.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service, get_keyring
from coffer.surfaces.http.schemas import KeychainSetIn

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


@router.delete(
    "/{ref}",
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
