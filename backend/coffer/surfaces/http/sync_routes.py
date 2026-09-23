"""/api/v1/sync — vault sync (spec vault-sync, ADR: vault-sync).

Sync is a cross-cutting service, not a resource kind, so it has its own routes
rather than riding /resources.

There is no export or import route. Writing a bundle to a directory and reading
one back was a wholesale overwrite with no base — the operation that caused the
2026-07-10 mutual deletion — and it has no place beside the diff-based round
(spec ``## Out of scope``). What replaces it: a new machine calls ``/adopt``, an
offline medium is a ``file://`` remote, and a hand-carried copy is a ``git
clone`` of the working tree.

The master key never travels inside the repository — moving it is a separate,
deliberate act. ``/key/export`` hands its material back over the token-guarded
loopback API and the caller decides where it lands; the daemon never writes to
a path a caller named, because a browser has no path to give it.

Remote shapes carry ``credential_ref`` and never the push credential itself, so
a remote can be rendered in a browser, logged, or pasted into a bug report with
nothing to redact.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from coffer.application.sync.joining import JoinPreview
from coffer.application.sync.machines import MachineRegistry, MachineView
from coffer.application.sync.service import ConvergeService
from coffer.domain.sync.backup import BackupRemote
from coffer.domain.sync.convergence import ConvergeRun, JoinKind, RunRecord
from coffer.domain.sync.diff import DiffSummary
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.sync_schemas import (
    AdoptIn,
    BreachOut,
    DiffCountsOut,
    DocChangeOut,
    FailureOut,
    JoinPreviewOut,
    KeyFingerprintOut,
    KeyImportOut,
    KeyMaterialIn,
    KeyMaterialOut,
    MachineListOut,
    MachineOut,
    MachineRemovedOut,
    MachineRenameIn,
    PendingConfirmationOut,
    RestoreIn,
    RoundOut,
    RunRecordOut,
    SyncRemoteClearedOut,
    SyncRemoteIn,
    SyncRemoteOut,
    SyncRemoteStateOut,
    SyncRunListOut,
    SyncStatusOut,
)

router = APIRouter(prefix="/api/v1/sync", tags=["sync"], dependencies=[Depends(require_token)])

_SERVICE: ConvergeService | None = None
_REGISTRY: MachineRegistry | None = None


def set_sync_service(service: ConvergeService) -> None:
    global _SERVICE
    _SERVICE = service


def get_sync_service() -> ConvergeService:
    if _SERVICE is None:
        raise RuntimeError("sync service not initialised")
    return _SERVICE


def set_machine_registry(registry: MachineRegistry) -> None:
    global _REGISTRY
    _REGISTRY = registry


def get_machine_registry() -> MachineRegistry:
    if _REGISTRY is None:
        raise RuntimeError("machine registry not initialised")
    return _REGISTRY


# --- projections -----------------------------------------------------------


def _remote_out(remote: BackupRemote) -> SyncRemoteOut:
    return SyncRemoteOut(
        url=remote.url,
        branch=remote.branch,
        credential_ref=remote.credential_ref,
        include_credentials=remote.include_credentials,
        interval_seconds=remote.interval_seconds,
        enabled=remote.enabled,
        worktree_path=remote.worktree_path,
    )


def _remote_or_none(remote: BackupRemote | None) -> SyncRemoteOut | None:
    return _remote_out(remote) if remote is not None else None


def _diff_out(diff: DiffSummary) -> DiffCountsOut:
    """A round's diff as both the tally and the paths behind it.

    The counts are what the history row shows; the changes are what opening
    the row is for. Sorted by ``DiffSummary.of`` already, so the order the
    reader sees is stable between rounds.
    """
    return DiffCountsOut(
        **diff.counts(),
        changes=[DocChangeOut(path=c.path, status=c.status) for c in diff.changes],
    )


def _round_out(run: ConvergeRun) -> RoundOut:
    pending = run.pending
    return RoundOut(
        status=run.status,
        join=run.join.value if run.join else None,
        applied=_diff_out(run.applied),
        published=_diff_out(run.published),
        commit=run.commit,
        conflicts=list(run.conflicts),
        agent_resolved=list(run.agent_resolved),
        failures=[FailureOut(path=p, reason=r) for p, r in run.failures],
        not_applicable=list(run.not_applicable),
        locked_refs=list(run.locked_refs),
        pending=PendingConfirmationOut(
            direction=pending.direction.value,
            breaches=[BreachOut(area=a, deleted=d, total=t) for a, d, t in pending.breaches],
            paths=list(pending.paths),
            raised_at=pending.raised_at,
        )
        if pending is not None
        else None,
        join_report=_preview_out(run.join_report) if run.join_report else None,
        error=run.error,
    )


def _record_out(record: RunRecord) -> RunRecordOut:
    """One history row: the same projection as any round, plus its timestamps.

    Built by widening ``_round_out`` rather than by projecting the round a
    second time — the history and the status page must describe an identical
    round identically, and two projections is how that stops being true.
    """
    run = record.run
    return RunRecordOut(
        id=record.id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        **_round_out(run).model_dump(),
    )


def _machine_out(view: MachineView) -> MachineOut:
    d = view.descriptor
    return MachineOut(
        machine_id=d.machine_id,
        name=d.name,
        os=d.os,
        hostname=d.hostname,
        coffer_version=d.coffer_version,
        last_converged_on=d.last_converged_on.isoformat() if d.last_converged_on else None,
        key_matches=view.key_matches,
        agents=list(d.agents),
        is_self=view.is_self,
    )


# --- rounds ----------------------------------------------------------------


@router.post("/run", response_model=RoundOut)
async def run_round() -> RoundOut:
    return _round_out(await get_sync_service().run_once())


def _preview_out(preview: JoinPreview) -> JoinPreviewOut:
    case: Literal["new", "returning", "ambiguous"] | None = (
        "ambiguous"
        if preview.ambiguous
        else (
            "returning" if preview.kind is JoinKind.RETURNING else "new" if preview.kind else None
        )
    )
    day = preview.last_converged_on
    return JoinPreviewOut(
        joining=preview.joining,
        case=case,
        base=preview.base,
        last_converged_on=day.isoformat() if day else None,
        remote_changed=preview.remote_changed,
        vault_documents=preview.vault_documents,
    )


@router.get("/join", response_model=JoinPreviewOut)
async def preview_join(
    choice: str | None = Query(default=None, pattern="^keep-local$"),
) -> JoinPreviewOut:
    """State the join ``/adopt`` would make, applying nothing.

    The surfaces call this first so the user sees the case, the day this
    machine last converged and the counts before a single document moves.
    """
    return _preview_out(await get_sync_service().preview_join(choice=choice))


@router.post("/adopt", response_model=RoundOut)
async def adopt(body: AdoptIn | None = None) -> RoundOut:
    """Join the configured remote.

    The same round as any other, and the only one allowed to join: ``/run``
    on a machine with no pointer reports ``awaiting_join``. Whether this is a
    join, and of which kind, is still read from the pointer and the registry,
    so configuring a remote on a machine that forgot its pointer cannot route
    around the new-versus-returning distinction. The surfaces call
    ``GET /join`` first and show its answer.
    """
    return _round_out(
        await get_sync_service().run_once(join_choice=(body.choice if body else None), adopt=True)
    )


@router.post("/confirm", response_model=RoundOut)
async def confirm() -> RoundOut:
    return _round_out(await get_sync_service().confirm())


@router.post("/reject", response_model=SyncRemoteClearedOut)
async def reject() -> SyncRemoteClearedOut:
    await get_sync_service().reject()
    return SyncRemoteClearedOut(cleared=True)


@router.post("/rebuild", response_model=RoundOut)
async def rebuild() -> RoundOut:
    """Rebuild this machine from the remote, discarding local-only documents.

    The answer for a machine whose vault is gone. Such a machine rejoins with a
    valid base and nothing to publish but the loss, so neither ordinary answer
    serves it: confirming spreads the loss and rejecting refuses the same round
    forever. Destructive on purpose.
    """
    return _round_out(await get_sync_service().rebuild())


@router.post("/rollback", response_model=RoundOut)
async def rollback() -> RoundOut:
    return _round_out(await get_sync_service().rollback())


@router.post("/restore", response_model=RoundOut)
async def restore(body: RestoreIn | None = None) -> RoundOut:
    svc = get_sync_service()
    return _round_out(await svc.restore(at=body.at if body else None))


# --- remote ----------------------------------------------------------------


@router.get("/remote", response_model=SyncRemoteStateOut)
async def get_remote() -> SyncRemoteStateOut:
    remote = await get_sync_service().get_remote()
    return SyncRemoteStateOut(configured=remote is not None, remote=_remote_or_none(remote))


@router.put("/remote", response_model=SyncRemoteOut)
async def put_remote(body: SyncRemoteIn) -> SyncRemoteOut:
    remote = await get_sync_service().set_remote(
        BackupRemote(
            url=body.url,
            branch=body.branch,
            credential_ref=body.credential_ref,
            include_credentials=body.include_credentials,
            interval_seconds=body.interval_seconds,
            enabled=body.enabled,
            worktree_path=body.worktree_path,
        )
    )
    return _remote_out(remote)


@router.delete("/remote", response_model=SyncRemoteClearedOut)
async def delete_remote() -> SyncRemoteClearedOut:
    return SyncRemoteClearedOut(cleared=await get_sync_service().clear_remote())


@router.get("/status", response_model=SyncStatusOut)
async def status() -> SyncStatusOut:
    svc = get_sync_service()
    registry = get_machine_registry()
    remote = await svc.get_remote()
    last = await svc.last_run()
    return SyncStatusOut(
        configured=remote is not None,
        remote=_remote_or_none(remote),
        last_run=_round_out(last) if last is not None else None,
        machine_id=registry.machine_id,
        machine_id_is_derived=registry.identity_is_derived,
        joined=await svc.joined(),
        not_applicable=await svc.not_applicable(),
    )


@router.get("/runs", response_model=SyncRunListOut)
async def list_runs(limit: int = Query(default=500, ge=1, le=500)) -> SyncRunListOut:
    """Every round this vault has run, newest first.

    Read-only and unfiltered. The surface searches, filters and pages in the
    browser over the window it is handed, the same way the Activity page does,
    so this route stays one query with one knob.
    """
    records = await get_sync_service().runs(limit)
    return SyncRunListOut(runs=[_record_out(r) for r in records])


# --- machines ---------------------------------------------------------------


@router.get("/machines", response_model=MachineListOut)
async def list_machines() -> MachineListOut:
    svc = get_sync_service()
    views = await svc.machines(get_machine_registry())
    return MachineListOut(machines=[_machine_out(v) for v in views])


@router.patch("/machines/self", response_model=MachineOut)
async def rename_self(body: MachineRenameIn) -> MachineOut:
    """Rename this machine.

    Free: ``scope`` references the derived id, never the label, so nothing
    else has to change.
    """
    view = await get_sync_service().rename_self(get_machine_registry(), body.name)
    return _machine_out(view)


@router.delete("/machines/{machine_id}", response_model=MachineRemovedOut)
async def retire_machine(machine_id: str) -> MachineRemovedOut:
    await get_sync_service().retire_machine(get_machine_registry(), machine_id)
    return MachineRemovedOut(removed=True)


# --- master key -------------------------------------------------------------


@router.get("/key/fingerprint", response_model=KeyFingerprintOut)
async def key_fingerprint() -> KeyFingerprintOut:
    return KeyFingerprintOut(fingerprint=get_sync_service().key_fingerprint())


@router.post("/key/export", response_model=KeyMaterialOut)
async def export_key() -> KeyMaterialOut:
    return KeyMaterialOut(material=await get_sync_service().export_key())


@router.post("/key/import", response_model=KeyImportOut)
async def import_key(body: KeyMaterialIn) -> KeyImportOut:
    return KeyImportOut(locked_refs=await get_sync_service().import_key(body.material))
