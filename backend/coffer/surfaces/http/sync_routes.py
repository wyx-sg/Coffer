"""/api/v1/sync — vault export and import (spec vault-export-import, ADR: vault-export-import).

Export/import is a cross-cutting service, not a resource kind, so it has its
own routes rather than riding /resources.

The master key never travels *inside* a bundle — moving it is a separate,
deliberate act. The key-export route hands its material back to the caller
over the token-guarded loopback API, and the caller decides where it lands (a
browser download, a file the CLI writes); the daemon no longer writes to a
path a caller named, because a browser has no path to give it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.sync.service import SyncService
from coffer.domain.sync.models import ExportSummary, ImportSummary
from coffer.surfaces.http.auth import require_token

router = APIRouter(prefix="/api/v1/sync", tags=["sync"], dependencies=[Depends(require_token)])

_SERVICE: SyncService | None = None


def set_sync_service(service: SyncService) -> None:
    global _SERVICE
    _SERVICE = service


def get_sync_service() -> SyncService:
    if _SERVICE is None:
        raise RuntimeError("sync service not initialised")
    return _SERVICE


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


def _areas(summary: ExportSummary | ImportSummary) -> list[AreaCountOut]:
    return [AreaCountOut(area=a.area, count=a.count) for a in summary.areas]


def _failures(summary: ExportSummary | ImportSummary) -> list[FailureOut]:
    return [FailureOut(ref=ref, reason=reason) for ref, reason in summary.failures]


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
    summary = await get_sync_service().import_bundle(body.path)
    return ImportOut(
        path=summary.path,
        areas=_areas(summary),
        failures=_failures(summary),
        locked_refs=summary.locked_refs,
    )


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
