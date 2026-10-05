"""The secret boundary's routes: approvals, presence grants, `coffer run`.

Spec secret "Release plaintext only to a present human in the desktop
app", "Hold a secret for a new destination until a person approves it",
and "Resolve standalone secrets into one child with coffer run"; ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.

Three kinds of route live here:

* **Presence-gated** — ``/presence/reveal``, ``/presence/master-key-export`` and
  ``/approvals/{id}/approve``. Each takes a one-time grant the desktop shell
  signs after its own LocalAuthentication check, bound to the operation and
  its target (``/presence/challenge`` issues it). These are the only routes
  that let plaintext out or widen where a secret goes, and they have no CLI
  counterpart on purpose: the CLI and the browser get "open the Coffer app".
* **Open** — listing and refusing approvals. Neither returns a value.
* **`coffer run`'s resolve** — answers standalone ``secret/<name>`` values
  only, and only those a person granted to local programs in the desktop app
  (the ``local_process`` binding, presence-gated, never a default); each answer
  is audited as ``secret_resolved``. The value is handed to the child the CLI
  starts, which is readable by whoever started it — an agent included — which
  is exactly why the grant is a person's decision. Asking for the grant, or
  withdrawing it, needs no presence: asking only waits, withdrawing only narrows.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
from typing import Any

from fastapi import APIRouter, Depends

from coffer.application.audit_service import AuditService
from coffer.application.secret.presence import CHALLENGE_TTL_SECONDS
from coffer.domain.audit import AuditEventType
from coffer.domain.secret_errors import (
    PresenceGrantInvalid,
    SecretBindingPending,
    SecretBindingRejected,
    SecretMissing,
    SecretNameInvalid,
    SecretNotFound,
)
from coffer.domain.secrets import (
    LOCAL_PROCESS_SLOT,
    SecretApproval,
    is_valid_secret_name,
    local_process_destination,
    secret_ref,
)
from coffer.domain.sync.errors import MasterKeyPassphraseTooShort
from coffer.infrastructure.secret import key_backup
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.secret_approval_routes import router as approval_router
from coffer.surfaces.http.secret_boundary_wiring import (
    get_presence_grants,
    get_secret_boundary,
)
from coffer.surfaces.http.secret_composition import (
    get_master_key_manager,
    get_secret_store,
)
from coffer.surfaces.http.secret_plaintext_routes import router as plaintext_router
from coffer.surfaces.http.secret_schemas import (
    LocalAccessIn,
    LocalAccessOut,
    MasterKeyExportIn,
    MasterKeyExportOut,
    PresenceChallengeIn,
    PresenceChallengeOut,
    PresenceStatusOut,
    ResolvedSecretsOut,
    ResolveSecretsIn,
    RevealedSecretOut,
    RevealIn,
)

router = APIRouter(
    prefix="/api/v1/secrets",
    tags=["secrets"],
    dependencies=[Depends(require_token)],
)
router.include_router(approval_router)
router.include_router(plaintext_router)


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
    store: Any = Depends(get_secret_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> RevealedSecretOut:
    """A secret's value, for the present human the desktop app just checked."""
    get_presence_grants().redeem("reveal", body.ref, body.nonce, body.signature)
    value = await asyncio.to_thread(store.peek, body.ref)
    if value is None:
        raise SecretMissing(body.ref)
    await audit.record(
        AuditEventType.SECRET_REVEALED.value, actor="desktop", details={"ref": body.ref}
    )
    return RevealedSecretOut(value=value)


@router.post("/presence/master-key-export", response_model=MasterKeyExportOut)
async def export_master_key(
    body: MasterKeyExportIn,
    manager: Any = Depends(get_master_key_manager),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> MasterKeyExportOut:
    """Write the passphrase-protected master key backup into the picked directory.

    The one way the key reaches a file (ADR master-key-lives-in-the-macos-
    keychain): a ``.cfk`` backup encrypted under the person's passphrase, mode
    ``0600``, a name of Coffer's choosing that never overwrites, and the key
    itself never crosses the API. The passphrase is checked before the grant
    is spent, so a short one costs no second presence check.
    """
    if len(body.passphrase) < key_backup.MIN_PASSPHRASE_LENGTH:
        raise MasterKeyPassphraseTooShort(key_backup.MIN_PASSPHRASE_LENGTH)
    get_presence_grants().redeem("export_master_key", body.directory, body.nonce, body.signature)
    directory = pathlib.Path(body.directory)
    if not directory.is_absolute() or not directory.is_dir():
        raise PresenceGrantInvalid(f"not a directory: {body.directory}")
    key = await asyncio.to_thread(manager.export_key)
    if not key:
        raise SecretMissing("master-key")
    text = await asyncio.to_thread(key_backup.wrap, key, body.passphrase)
    path = await asyncio.to_thread(_write_new_file, directory, key_backup.BACKUP_FILE_NAME, text)
    fingerprint = key_backup.key_fingerprint(key)
    await audit.record(
        AuditEventType.MASTER_KEY_EXPORTED.value,
        actor="desktop",
        details={"path": str(path), "fingerprint": fingerprint},
    )
    return MasterKeyExportOut(path=str(path), fingerprint=fingerprint)


def _write_new_file(directory: pathlib.Path, name: str, text: str) -> pathlib.Path:
    """Write ``text`` to ``name`` in ``directory``, numbering it rather than overwriting."""
    stem, suffix = os.path.splitext(name)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for n in range(1, 100):
        path = directory / (name if n == 1 else f"{stem}-{n}{suffix}")
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return path
    raise PresenceGrantInvalid(f"too many key backups already in {directory}")


# --- coffer run ------------------------------------------------------------------


async def _ask_local(names: list[str], actor: str, audit: AuditService) -> list[SecretApproval]:
    """The local-process approvals ``names`` still wait on (empty: all granted).
    A request made here for the first time is audited as asked for."""
    boundary = get_secret_boundary()
    dest = local_process_destination()
    before = {a.id for a in await asyncio.to_thread(boundary.list, status="pending")}
    waiting: list[SecretApproval] = []
    for name in names:
        waiting += await asyncio.to_thread(
            boundary.check, dest, {LOCAL_PROCESS_SLOT: secret_ref(name)}, actor=actor
        )
    for approval in waiting:
        if approval.status == "pending" and approval.id not in before:
            await audit.record(
                AuditEventType.SECRET_APPROVAL_REQUESTED.value,
                actor=actor,
                details={"approval_id": approval.id, "op": approval.op, "ref": approval.ref},
            )
    return waiting


def _check_names(names: list[str], store: Any) -> list[str]:
    wanted = list(dict.fromkeys(names))
    for name in wanted:
        if not is_valid_secret_name(name):
            raise SecretNameInvalid(name)
        if not store.exists(secret_ref(name)):
            raise SecretNotFound(name)
    return wanted


@router.post("/resolve", response_model=ResolvedSecretsOut)
async def resolve_for_run(
    body: ResolveSecretsIn,
    store: Any = Depends(get_secret_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ResolvedSecretsOut:
    """Standalone secrets for one `coffer run` child — never a resource's secret,
    and only those a person granted to local programs.

    A resource's secret (an MCP token, a provider key, a channel token) is not
    a ``secret/`` name and so is not answerable here: it goes only to the
    destination it was approved for. A standalone secret without the
    local-process grant is refused (``SECRET_BINDING_PENDING``, the request now
    waiting in the desktop app; ``SECRET_BINDING_REJECTED`` once refused) and no
    value is read. The grant does not depend on the approval switch or the
    build: whoever runs ``coffer run`` — an agent too — can read what it is
    handed, so only a person's approval lets a value out this way.
    """
    wanted = await asyncio.to_thread(_check_names, body.names, store)
    waiting = await _ask_local(wanted, actor, audit)
    refused = [a for a in waiting if a.status == "rejected"]
    if refused:
        raise SecretBindingRejected([a.id for a in refused], [a.describe() for a in refused])
    if waiting:
        raise SecretBindingPending([a.id for a in waiting], [a.describe() for a in waiting])
    values: dict[str, str] = {}
    for name in wanted:
        value = await asyncio.to_thread(store.get, secret_ref(name))
        if value is None:
            raise SecretNotFound(name)
        values[name] = value
    for name in values:
        await audit.record(
            AuditEventType.SECRET_RESOLVED.value,
            actor=actor,
            details={
                "ref": secret_ref(name),
                "name": name,
                "argv0": body.argv0,
                "cwd": body.cwd,
            },
        )
    return ResolvedSecretsOut(values=values)


@router.post("/local-access/request", response_model=LocalAccessOut)
async def request_local_access(
    body: LocalAccessIn,
    store: Any = Depends(get_secret_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> LocalAccessOut:
    """Ask for a standalone secret's local-process grant. Only records the
    request: the grant takes a person's approval in the desktop app."""
    (name,) = await asyncio.to_thread(_check_names, [body.name], store)
    waiting = await _ask_local([name], actor, audit)
    if not waiting:
        return LocalAccessOut(local_access="on")
    if waiting[0].status == "rejected":
        raise SecretBindingRejected([waiting[0].id], [waiting[0].describe()])
    return LocalAccessOut(local_access="pending", approval_id=waiting[0].id)


@router.post("/local-access/revoke", response_model=LocalAccessOut)
async def revoke_local_access(
    body: LocalAccessIn,
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> LocalAccessOut:
    """Withdraw a standalone secret's local-process grant (and any request for
    it). Needs no presence: it only narrows."""
    if not is_valid_secret_name(body.name):
        raise SecretNameInvalid(body.name)
    ref = secret_ref(body.name)
    had = await asyncio.to_thread(get_secret_boundary().revoke_local, ref)
    if had:
        await audit.record(
            AuditEventType.SECRET_LOCAL_ACCESS_REVOKED.value, actor=actor, details={"ref": ref}
        )
    return LocalAccessOut(local_access="off")
