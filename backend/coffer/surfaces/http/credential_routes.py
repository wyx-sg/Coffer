# backend/coffer/surfaces/http/credential_routes.py
"""/api/v1/credentials — read and write secrets in the encrypted credential store.

Secrets are Fernet-encrypted into the coffer DB; only ciphertext is persisted;
audit rows carry the ref only — secret values never appear in the audit log.

The UI uses this when importing MCP server JSON: any plaintext secret in the
pasted `env` is lifted into the credential store here, so it never lands in
Coffer's resource config unencrypted — the resource config only keeps a
credential ref.

Every lifecycle change is audited (FR-014). The audit row records the `ref`
only — secret values never appear in the audit log.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service, get_credential_store
from coffer.surfaces.http.schemas import (
    CredentialExistsOut,
    CredentialGetOut,
    CredentialSetIn,
)

router = APIRouter(
    prefix="/api/v1/credentials",
    tags=["credentials"],
    dependencies=[Depends(require_token)],
)


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def set_secret(
    body: CredentialSetIn,
    store: Any = Depends(get_credential_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Store `value` under `ref` in the encrypted credential store."""
    store.set(body.ref, body.value)
    await audit.record(
        AuditEventType.CREDENTIAL_SET.value,
        actor=actor,
        details={"ref": body.ref},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# NOTE: /exists is declared BEFORE the value route — both use `{ref:path}`
# (refs may contain slashes, e.g. channel tokens), so declaration order is
# what keeps `/x/exists` from being swallowed by the value route.
@router.get("/{ref:path}/exists", response_model=CredentialExistsOut)
async def secret_exists(
    ref: str,
    store: Any = Depends(get_credential_store),  # noqa: B008
) -> CredentialExistsOut:
    """Report whether a secret is stored under `ref`.

    Presence only — the value is never decrypted or read out for this check,
    so no audit event is recorded and a corrupt (undecryptable) row can't
    500 the probe; it still reports present.
    """
    return CredentialExistsOut(present=store.exists(ref))


@router.get("/{ref:path}", response_model=CredentialGetOut)
async def get_secret(
    ref: str,
    store: Any = Depends(get_credential_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> CredentialGetOut:
    """Return the secret value stored under `ref`.

    Reading a value out is audited (ref only — the value never reaches the
    audit row), so explicit secret reads leave a trail. 404 when absent.
    """
    value = store.get(ref)
    if value is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await audit.record(
        AuditEventType.CREDENTIAL_READ.value,
        actor=actor,
        details={"ref": ref},
    )
    return CredentialGetOut(value=value)



@router.delete(
    "/{ref:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_secret(
    ref: str,
    store: Any = Depends(get_credential_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Remove `ref` from the credential store. Idempotent — absent is fine."""
    store.delete(ref)
    await audit.record(
        AuditEventType.CREDENTIAL_DELETED.value,
        actor=actor,
        details={"ref": ref},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
