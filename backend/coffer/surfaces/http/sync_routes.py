"""/api/v1/sync — vault export and import (spec vault-export-import, ADR: vault-export-import).

Export/import is a cross-cutting service, not a resource kind, so it has its
own routes rather than riding /resources.

The master key never travels *inside* a bundle — moving it is a separate,
deliberate act. The key-export route hands its material back to the caller
over the token-guarded loopback API, and the caller decides where it lands (a
browser download, a file the CLI writes); the daemon no longer writes to a
path a caller named, because a browser has no path to give it.

The backup half of this surface (``/remote``, ``/push``, ``/restore``,
``/status``) configures and drives the one git remote exports are pushed to
(spec ``## Backup``). Its wire shapes carry ``credential_ref`` and never the
push credential itself: the ref is a name in the credential store, so a remote
can be rendered in a browser, logged, or pasted into a bug report without
anything to redact.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.sync.backup_service import BackupService
from coffer.application.sync.service import SyncService
from coffer.domain.sync.backup import (
    DEFAULT_BRANCH,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_WORKTREE,
    BackupRemote,
    BackupRun,
)
from coffer.domain.sync.models import ExportSummary, ImportSummary
from coffer.surfaces.http.auth import require_token

router = APIRouter(prefix="/api/v1/sync", tags=["sync"], dependencies=[Depends(require_token)])

_SERVICE: SyncService | None = None
_BACKUP: BackupService | None = None


def set_sync_service(service: SyncService) -> None:
    global _SERVICE
    _SERVICE = service


def get_sync_service() -> SyncService:
    if _SERVICE is None:
        raise RuntimeError("sync service not initialised")
    return _SERVICE


def set_backup_service(service: BackupService) -> None:
    global _BACKUP
    _BACKUP = service


def get_backup_service() -> BackupService:
    if _BACKUP is None:
        raise RuntimeError("backup service not initialised")
    return _BACKUP


# --- schemas ---------------------------------------------------------------


class AreaCountOut(BaseModel):
    area: str
    count: int


class FailureOut(BaseModel):
    ref: str
    reason: str


class ExportIn(BaseModel):
    path: str
    # Off by default: an export directory is easy to leave somewhere careless
    # (spec vault-export-import "Credentials").
    with_credentials: bool = False


class ExportOut(BaseModel):
    path: str
    areas: list[AreaCountOut]
    failures: list[FailureOut]
    credentials_included: bool


class ImportIn(BaseModel):
    path: str


class ImportOut(BaseModel):
    path: str
    areas: list[AreaCountOut]
    failures: list[FailureOut]
    locked_refs: list[str]


class KeyMaterialIn(BaseModel):
    material: str


class KeyMaterialOut(BaseModel):
    #: The Fernet key text. Crosses only the token-guarded loopback API — the
    #: caller decides where it lands (a browser download, a file the CLI
    #: writes), because a browser has no path to hand the daemon.
    material: str


class KeyImportOut(BaseModel):
    locked_refs: list[str]


class KeyFingerprintOut(BaseModel):
    present: bool
    # Short SHA-256 fingerprint of the master key (never the key itself);
    # matching fingerprints on two machines = the same key.
    fingerprint: str | None


class BackupRemoteIn(BaseModel):
    """The backup remote as the user configures it.

    Every field but the URL has the spec's default, so ``PUT`` with a bare URL
    is a complete configuration rather than a half-set one.
    """

    url: str
    branch: str = DEFAULT_BRANCH
    #: A name in the credential store — never the secret. The daemon resolves
    #: it at push time and nowhere else.
    credential_ref: str | None = None
    include_credentials: bool = False
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    enabled: bool = True
    worktree_path: str = DEFAULT_WORKTREE


class BackupRemoteOut(BaseModel):
    """What the daemon reports back about the remote.

    Deliberately the same fields it was given, minus nothing and plus nothing:
    the push credential is absent because it was never stored here in the
    first place (spec ``## Backup``).
    """

    url: str
    branch: str
    credential_ref: str | None
    include_credentials: bool
    interval_seconds: int
    enabled: bool
    worktree_path: str


class BackupRemoteStateOut(BaseModel):
    #: ``False`` on a fresh vault. Backup being off is the ordinary state, not
    #: an error, so an unconfigured remote is a 200 with ``remote: null``.
    configured: bool
    remote: BackupRemoteOut | None


class BackupRemoteClearedOut(BaseModel):
    #: ``False`` when there was nothing to clear — delete is idempotent.
    cleared: bool


class BackupRunOut(BaseModel):
    """One run's outcome. ``error`` is already redacted of any token."""

    status: str
    commit: str | None
    error: str | None
    ran_at: datetime | None


class BackupStatusOut(BaseModel):
    configured: bool
    remote: BackupRemoteOut | None
    last_run: BackupRunOut | None


class RestoreIn(BaseModel):
    #: A sha, a ref, or a ``YYYY-MM-DD`` date resolving to the last commit at
    #: or before it — the tip cannot return something deleted last week.
    at: str | None = None
    #: Restore onto a machine that has no working tree yet: clone from here.
    from_url: str | None = None


def _areas(summary: ExportSummary | ImportSummary) -> list[AreaCountOut]:
    return [AreaCountOut(area=a.area, count=a.count) for a in summary.areas]


def _failures(summary: ExportSummary | ImportSummary) -> list[FailureOut]:
    return [FailureOut(ref=ref, reason=reason) for ref, reason in summary.failures]


def _remote_out(remote: BackupRemote) -> BackupRemoteOut:
    return BackupRemoteOut(
        url=remote.url,
        branch=remote.branch,
        credential_ref=remote.credential_ref,
        include_credentials=remote.include_credentials,
        interval_seconds=remote.interval_seconds,
        enabled=remote.enabled,
        worktree_path=remote.worktree_path,
    )


def _remote_or_none(remote: BackupRemote | None) -> BackupRemoteOut | None:
    return None if remote is None else _remote_out(remote)


def _run_out(run: BackupRun) -> BackupRunOut:
    return BackupRunOut(
        status=str(run.status), commit=run.commit, error=run.error, ran_at=run.ran_at
    )


def _import_out(summary: ImportSummary) -> ImportOut:
    return ImportOut(
        path=summary.path,
        areas=_areas(summary),
        failures=_failures(summary),
        locked_refs=summary.locked_refs,
    )


# --- routes ----------------------------------------------------------------


@router.post("/export", response_model=ExportOut)
async def export_bundle(body: ExportIn) -> ExportOut:
    summary = await get_sync_service().export_bundle(
        body.path, with_credentials=body.with_credentials
    )
    return ExportOut(
        path=summary.path,
        areas=_areas(summary),
        failures=_failures(summary),
        credentials_included=summary.credentials_included,
    )


@router.post("/import", response_model=ImportOut)
async def import_bundle(body: ImportIn) -> ImportOut:
    return _import_out(await get_sync_service().import_bundle(body.path))


@router.get("/key/fingerprint", response_model=KeyFingerprintOut)
async def key_fingerprint() -> KeyFingerprintOut:
    fp = get_sync_service().key_fingerprint()
    return KeyFingerprintOut(present=fp is not None, fingerprint=fp)


@router.post("/key/export", response_model=KeyMaterialOut)
async def export_key() -> KeyMaterialOut:
    return KeyMaterialOut(material=await get_sync_service().export_key())


@router.post("/key/import", response_model=KeyImportOut)
async def import_key(body: KeyMaterialIn) -> KeyImportOut:
    return KeyImportOut(locked_refs=await get_sync_service().import_key(body.material))


# --- backup routes (spec vault-export-import ``## Backup``) -----------------


@router.get("/remote", response_model=BackupRemoteStateOut)
async def get_backup_remote() -> BackupRemoteStateOut:
    """Report the configured remote — its ref, never its credential."""
    remote = await get_backup_service().get()
    return BackupRemoteStateOut(configured=remote is not None, remote=_remote_or_none(remote))


@router.put("/remote", response_model=BackupRemoteOut)
async def put_backup_remote(body: BackupRemoteIn) -> BackupRemoteOut:
    """Configure the one backup remote, replacing any previous one.

    Validation lives in the domain object: constructing ``BackupRemote``
    raises ``BackupRemoteInvalid`` (422) for an empty URL or branch or a
    non-positive interval, so the same rules hold for every surface.
    """
    remote = BackupRemote(**body.model_dump())
    await get_backup_service().configure(remote)
    return _remote_out(remote)


@router.delete("/remote", response_model=BackupRemoteClearedOut)
async def delete_backup_remote() -> BackupRemoteClearedOut:
    """Turn backup off. The working tree and its history are left alone —
    they are the local layer of recovery and are not ours to destroy."""
    service = get_backup_service()
    existed = await service.get() is not None
    await service.clear()
    return BackupRemoteClearedOut(cleared=existed)


@router.post("/push", response_model=BackupRunOut)
async def push_backup() -> BackupRunOut:
    """Run one backup now and report what it did.

    A run that could not push is a 200 carrying ``push_failed``, not an error
    status: the commit exists locally, the next run carries it out, and the
    caller wants the run's story rather than an exception.
    """
    return _run_out(await get_backup_service().run_once())


@router.post("/restore", response_model=ImportOut)
async def restore_backup(body: RestoreIn | None = None) -> ImportOut:
    """Fetch the backup, optionally move to an earlier revision, then import.

    Only ever reached because a user asked: nothing restores on a timer.
    """
    body = body or RestoreIn()
    summary = await get_backup_service().restore(at=body.at, from_url=body.from_url)
    return _import_out(summary)


@router.get("/status", response_model=BackupStatusOut)
async def backup_status() -> BackupStatusOut:
    """The remote and its last run — the pair the CLI and the UI both render."""
    remote, run = await get_backup_service().status()
    return BackupStatusOut(
        configured=remote is not None,
        remote=_remote_or_none(remote),
        last_run=None if run is None else _run_out(run),
    )
