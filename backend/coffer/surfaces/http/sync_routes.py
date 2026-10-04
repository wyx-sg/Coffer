"""/api/v1/sync — status, rounds, the remote, machines and the master key
(spec vault-sync; ADR sync-applies-clean-merges-and-stops-on-any-conflict).

Sync is a cross-cutting service, not a resource kind, so it has its own
routes. What a round waiting for a person needs — the stopped files, a hold,
a join and its choices, a rollback — is in ``sync_stop_routes``, on the same
router.

No route returns the master key: a backup is written only by the desktop
app's presence-gated export (spec secret "Release plaintext only to a
present human in the desktop app"). ``/key/import`` takes key material in — a
caller that supplies a key already has it — and ``/key/import/preview`` says
whose key a file holds before anything is replaced.
"""

from __future__ import annotations

from fastapi import Query

from coffer.domain.sync.remote import SyncRemote
from coffer.surfaces.http import sync_stop_routes as _stop_routes  # noqa: F401  (registers)
from coffer.surfaces.http.sync_dependencies import get_sync_service, router
from coffer.surfaces.http.sync_projections import machine_out, remote_out, round_out, status_out
from coffer.surfaces.http.sync_schemas import (
    KeyFingerprintOut,
    KeyImportIn,
    KeyImportOut,
    KeyMaterialIn,
    KeyPreviewOut,
    MachineListOut,
    MachineOut,
    MachineRemovedOut,
    MachineRenameIn,
    RemoteCheckIn,
    RemoteCheckOut,
    RoundOut,
    SyncRemoteClearedOut,
    SyncRemoteIn,
    SyncRemoteOut,
    SyncRemoteStateOut,
    SyncRunListOut,
    SyncStatusOut,
    VaultMoveIn,
    VaultMoveOut,
)

_ACTOR = "user"


# --- status and rounds ----------------------------------------------------------


@router.get("/status", response_model=SyncStatusOut)
async def status() -> SyncStatusOut:
    return status_out(await get_sync_service().status())


@router.post("/run", response_model=RoundOut)
async def run_round() -> RoundOut:
    """One round now. Never an error for what the round ran into: an
    unreachable remote or a conflict is the round's recorded status."""
    return round_out(await get_sync_service().run(trigger="manual"))


@router.get("/runs", response_model=SyncRunListOut)
async def list_runs(
    limit: int = Query(default=50, ge=1, le=500),
    cursor: str | None = Query(
        default=None,
        description="The previous page's next_cursor; any other value is 400 CURSOR_INVALID.",
    ),
) -> SyncRunListOut:
    """Every round this machine ran, newest first."""
    page = await get_sync_service().rounds(limit=limit, cursor=cursor)
    return SyncRunListOut(
        rounds=[round_out(r) for r in page.rounds], total=page.total, next_cursor=page.next_cursor
    )


@router.get("/runs/{run_id}", response_model=RoundOut)
async def get_run(run_id: int) -> RoundOut:
    return round_out(await get_sync_service().round(run_id))


# --- the remote -------------------------------------------------------------------


@router.get("/remote", response_model=SyncRemoteStateOut)
async def get_remote() -> SyncRemoteStateOut:
    remote = await get_sync_service().get_remote()
    return SyncRemoteStateOut(
        configured=remote is not None, remote=remote_out(remote) if remote else None
    )


@router.put("/remote", response_model=SyncRemoteOut)
async def put_remote(body: SyncRemoteIn) -> SyncRemoteOut:
    remote = await get_sync_service().set_remote(
        SyncRemote(
            url=body.url,
            branch=body.branch,
            secret_ref=body.secret_ref,
            include_secret=body.include_secret,
            interval_seconds=body.interval_seconds,
            enabled=body.enabled,
        )
    )
    return remote_out(remote)


@router.delete("/remote", response_model=SyncRemoteClearedOut)
async def delete_remote() -> SyncRemoteClearedOut:
    """Stop syncing: forget the remote. The vault and its history stay. No
    confirmation: ``POST /remote/restore`` puts it back while nothing else is set."""
    cleared = await get_sync_service().clear_remote()
    return SyncRemoteClearedOut(cleared=cleared, restorable=cleared)


@router.post("/remote/restore", response_model=SyncRemoteOut)
async def restore_remote() -> SyncRemoteOut:
    """Undo Stop syncing: the remote that was forgotten (its push secret is
    still only a name), and what this machine knew about it. 409
    ``SYNC_NOTHING_TO_RESTORE`` when none was stopped, ``SYNC_REMOTE_EXISTS``
    when another is set."""
    return remote_out(await get_sync_service().restore_remote())


@router.post("/remote/check", response_model=RemoteCheckOut)
async def check_remote(body: RemoteCheckIn) -> RemoteCheckOut:
    """What a remote holds, before it is saved: nothing is kept."""
    found = await get_sync_service().check_remote(body.url, body.branch, body.secret_ref)
    return RemoteCheckOut(
        result=found.result,  # type: ignore[arg-type]
        tip=found.tip,
        layout=found.layout,
        detail=found.detail,
    )


# --- the vault's place ----------------------------------------------------------------


@router.post("/vault/move", response_model=VaultMoveOut, response_model_by_alias=True)
async def move_vault(body: VaultMoveIn) -> VaultMoveOut:
    """Move the vault out of a synchronised folder: rounds and writes are held
    off, the folder is moved and its git repository checked at the new place.
    The old folder is left empty. 422 ``SYNC_VAULT_TARGET_INVALID`` /
    ``SYNC_VAULT_TARGET_IN_CLOUD``, 409 ``SYNC_VAULT_TARGET_NOT_EMPTY``, 500
    ``SYNC_VAULT_MOVE_FAILED`` (the vault is back where it was)."""
    moved = await get_sync_service().move_vault(body.to)
    return VaultMoveOut.model_validate({"from": moved.origin, "to": moved.target})


# --- machines -----------------------------------------------------------------------


@router.get("/machines", response_model=MachineListOut)
async def list_machines() -> MachineListOut:
    return MachineListOut(machines=[machine_out(v) for v in await get_sync_service().machines()])


@router.patch("/machines/self", response_model=MachineOut)
async def rename_self(body: MachineRenameIn) -> MachineOut:
    """Rename this machine. Free: nothing keys on the label."""
    return machine_out(await get_sync_service().rename_self(body.name, actor=_ACTOR))


@router.delete("/machines/{machine_id}", response_model=MachineRemovedOut)
async def retire_machine(machine_id: str) -> MachineRemovedOut:
    """Retire another machine: its descriptor goes, in a commit of yours; no
    confirmation, ``POST /machines/{id}/restore`` registers it again."""
    await get_sync_service().retire_machine(machine_id, actor=_ACTOR)
    return MachineRemovedOut(removed=True)


@router.post("/machines/{machine_id}/restore", response_model=MachineOut)
async def restore_machine(machine_id: str) -> MachineOut:
    """Undo a retire: register the machine again with the descriptor it had.
    404 ``SYNC_MACHINE_NOT_FOUND`` when it was never registered here."""
    return machine_out(await get_sync_service().restore_machine(machine_id, actor=_ACTOR))


# --- the master key -------------------------------------------------------------------


@router.get("/key/fingerprint", response_model=KeyFingerprintOut)
async def key_fingerprint() -> KeyFingerprintOut:
    return KeyFingerprintOut(fingerprint=get_sync_service().key_fingerprint())


@router.post("/key/import/preview", response_model=KeyPreviewOut)
async def preview_key_import(body: KeyMaterialIn) -> KeyPreviewOut:
    """Whose key a file holds and whether it is this machine's, changing nothing.

    A passphrase-protected backup is not opened here: its fingerprint is read
    from the file and checked against the key when it is imported.
    """
    preview = get_sync_service().preview_key(body.material)
    return KeyPreviewOut(
        fingerprint=preview.fingerprint,
        current_fingerprint=preview.current,
        same=preview.fingerprint == preview.current,
        protected=preview.protected,
    )


@router.post("/key/import", response_model=KeyImportOut)
async def import_key(body: KeyImportIn) -> KeyImportOut:
    result = await get_sync_service().import_key(body.material, body.passphrase)
    return KeyImportOut(
        fingerprint=result.fingerprint,
        replaced=result.replaced,
        readable=result.readable,
        locked_refs=result.locked_refs,
    )


__all__ = ["router"]
