"""The secret boundary's routes: approvals, presence grants, `coffer run`, the scan.

Spec credentials "Release plaintext only to a present human in the desktop
app", "Hold a secret for a new destination until a person approves it",
"Resolve standalone secrets into one child with coffer run" and "Move
plaintext secret files into the store"; ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.

Three kinds of route live here:

* **Presence-gated** — ``/presence/reveal``, ``/presence/master-key-export`` and
  ``/approvals/{id}/approve``. Each takes a one-time grant the desktop shell
  signs after its own LocalAuthentication check, bound to the operation and
  its target (``/presence/challenge`` issues it). These are the only routes
  that let plaintext out or widen where a secret goes, and they have no CLI
  counterpart on purpose: the CLI and the browser get "open the Coffer app".
* **Open** — listing and refusing approvals, the scan and the move of
  plaintext files into the store. None of them returns a value.
* **`coffer run`'s resolve** — answers standalone ``secret/<name>`` values
  only, each audited as ``secret_resolved``. The value is handed to the child
  the CLI starts, which is readable by the agent that ran the command; the docs
  and the UI say so.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import pathlib
from typing import Any

from fastapi import APIRouter, Depends, Query

from coffer.application.audit_service import AuditService
from coffer.application.credentials.presence import CHALLENGE_TTL_SECONDS
from coffer.application.knowledge.guide_render import GUIDE_SKILL_NAME
from coffer.domain.audit import AuditEventType
from coffer.domain.credential_errors import (
    CredentialMissing,
    PresenceGrantInvalid,
    SecretNameInvalid,
    SecretNotFound,
)
from coffer.domain.secrets import is_valid_secret_name, secret_ref, secret_uri
from coffer.infrastructure.credentials import plaintext_scan
from coffer.infrastructure.sync.identity import coffer_dir
from coffer.infrastructure.sync.paths import skills_root
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.credential_composition import (
    get_credential_store,
    get_master_key_manager,
)
from coffer.surfaces.http.credential_schemas import (
    ApprovalListOut,
    ApprovalOut,
    MasterKeyExportIn,
    MasterKeyExportOut,
    PresenceChallengeIn,
    PresenceChallengeOut,
    PresenceGrantIn,
    PresenceStatusOut,
    ResolvedSecretsOut,
    ResolveSecretsIn,
    RevealedSecretOut,
    RevealIn,
    SecretImportIn,
    SecretImportMovedOut,
    SecretImportOut,
    SecretImportSkippedOut,
    SecretScanFindingOut,
    SecretScanMentionOut,
    SecretScanOut,
)
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.secret_boundary_wiring import (
    approval_applied,
    approval_out,
    get_presence_grants,
    get_secret_boundary,
    refresh_approvals,
)

router = APIRouter(
    prefix="/api/v1/credentials",
    tags=["credentials"],
    dependencies=[Depends(require_token)],
)


#: Skills Coffer renders itself: its guide quotes `coffer run --secret …` on purpose.
_COFFERS_OWN_SKILLS = frozenset({GUIDE_SKILL_NAME})


def _secrets_dir() -> pathlib.Path:
    return coffer_dir() / "secrets"


# --- approvals ---------------------------------------------------------------


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


# --- presence ------------------------------------------------------------------


@router.get("/presence/status", response_model=PresenceStatusOut)
async def presence_status(manager: Any = Depends(get_master_key_manager)) -> PresenceStatusOut:  # noqa: B008
    return PresenceStatusOut(
        master_key_storage=manager.location, development=bool(manager.development)
    )


@router.post("/presence/challenge", response_model=PresenceChallengeOut)
async def presence_challenge(body: PresenceChallengeIn) -> PresenceChallengeOut:
    """A one-time nonce for one operation on one target; the shell signs it."""
    issued = get_presence_grants().challenge(body.op, body.target)
    return PresenceChallengeOut(
        nonce=issued.nonce,
        op=body.op,
        target=body.target,
        expires_in_seconds=int(CHALLENGE_TTL_SECONDS),
    )


@router.post("/presence/reveal", response_model=RevealedSecretOut)
async def reveal(
    body: RevealIn,
    store: Any = Depends(get_credential_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> RevealedSecretOut:
    """A secret's value, for the present human the desktop app just checked."""
    get_presence_grants().redeem("reveal", body.ref, body.nonce, body.signature)
    value = await asyncio.to_thread(store.get, body.ref)
    if value is None:
        raise CredentialMissing(body.ref)
    await audit.record(
        AuditEventType.CREDENTIAL_REVEALED.value, actor="desktop", details={"ref": body.ref}
    )
    return RevealedSecretOut(value=value)


@router.post("/presence/master-key-export", response_model=MasterKeyExportOut)
async def export_master_key(
    body: MasterKeyExportIn,
    manager: Any = Depends(get_master_key_manager),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> MasterKeyExportOut:
    """Write the master key backup into the directory the person picked.

    The one way the key reaches a file (ADR master-key-lives-in-the-macos-
    keychain): mode ``0600``, a name of Coffer's choosing that never
    overwrites, and the key itself never crosses the API.
    """
    get_presence_grants().redeem("export_master_key", body.directory, body.nonce, body.signature)
    directory = pathlib.Path(body.directory)
    if not directory.is_absolute() or not directory.is_dir():
        raise PresenceGrantInvalid(f"not a directory: {body.directory}")
    key = await asyncio.to_thread(manager.export_key)
    if not key:
        raise CredentialMissing("master-key")
    fingerprint = hashlib.sha256(key).hexdigest()[:12]
    path = directory / f"coffer-master-key-{fingerprint}.key"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key + b"\n")
    await audit.record(
        AuditEventType.MASTER_KEY_EXPORTED.value,
        actor="desktop",
        details={"path": str(path), "fingerprint": fingerprint},
    )
    return MasterKeyExportOut(path=str(path), fingerprint=fingerprint)


# --- coffer run ------------------------------------------------------------------


@router.post("/secrets/resolve", response_model=ResolvedSecretsOut)
async def resolve_for_run(
    body: ResolveSecretsIn,
    store: Any = Depends(get_credential_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ResolvedSecretsOut:
    """Standalone secrets for one `coffer run` child — never a resource's secret.

    A resource's secret (an MCP token, a provider key, a channel token) is not
    a ``secret/`` name and so is not answerable here: it goes only to the
    destination it was approved for.
    """
    values: dict[str, str] = {}
    for name in dict.fromkeys(body.names):
        if not is_valid_secret_name(name):
            raise SecretNameInvalid(name)
        value = await asyncio.to_thread(store.get, secret_ref(name))
        if value is None:
            raise SecretNotFound(name)
        values[name] = value
    for name in values:
        await audit.record(
            AuditEventType.SECRET_RESOLVED.value,
            actor=actor,
            details={"name": name, "argv0": body.argv0, "cwd": body.cwd},
        )
    return ResolvedSecretsOut(values=values)


# --- plaintext files --------------------------------------------------------------


@router.post("/scan", response_model=SecretScanOut)
async def scan_plaintext() -> SecretScanOut:
    """Plaintext secrets in ``~/.coffer/secrets/`` and the skill master store."""
    result = await asyncio.to_thread(
        plaintext_scan.scan, _secrets_dir(), skills_root(), _COFFERS_OWN_SKILLS
    )
    return SecretScanOut(
        findings=[
            SecretScanFindingOut(
                id=f.id,
                path=f.path,
                source=f.source,  # type: ignore[arg-type]
                key=f.key,
                line=f.line,
                proposed_name=f.proposed_name,
            )
            for f in result.findings
        ],
        mentions=[
            SecretScanMentionOut(skill=m.skill, path=m.path, line=m.line, mention=m.mention)
            for m in result.mentions
        ],
    )


@router.post("/import", response_model=SecretImportOut)
async def import_plaintext(
    body: SecretImportIn,
    store: Any = Depends(get_credential_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> SecretImportOut:
    """Move plaintext findings into the store, replacing each with its reference."""

    def put(name: str, value: str) -> bool:
        ref = secret_ref(name)
        existing = store.get(ref)
        if existing is not None:
            return bool(existing == value)
        store.set(ref, value)
        # Read back and compare: the file is rewritten only once the store
        # provably holds the same bytes.
        return bool(store.get(ref) == value)

    result = await asyncio.to_thread(
        plaintext_scan.move,
        _secrets_dir(),
        skills_root(),
        body.ids,
        store=put,
        dry_run=body.dry_run,
        skip=_COFFERS_OWN_SKILLS,
    )
    if not result.dry_run:
        for moved in result.moved:
            await audit.record(
                AuditEventType.SECRET_IMPORTED.value,
                actor=actor,
                details={"name": moved.name, "path": moved.path},
            )
    return SecretImportOut(
        moved=[
            SecretImportMovedOut(id=m.id, path=m.path, name=m.name, uri=secret_uri(m.name))
            for m in result.moved
        ],
        skipped=[
            SecretImportSkippedOut(id=s.id, path=s.path, reason=s.reason) for s in result.skipped
        ],
        dry_run=result.dry_run,
    )
