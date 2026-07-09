"""/api/v1/sync — multi-machine sync (spec 010).

Sync is a cross-cutting service, not a resource kind, so it has its own routes
rather than riding /resources. The master key is never returned over the wire;
the key-export route writes it to a local file path the user then moves
out-of-band.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from coffer.application.sync.service import SyncService
from coffer.domain.sync.models import (
    DEFAULT_BRANCH,
    DEFAULT_INTERVAL_SECONDS,
    SyncConfig,
    SyncState,
)
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor

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


class SyncConfigIn(BaseModel):
    remote: str | None = None
    enabled: bool = False
    auto: bool = False
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    branch: str = DEFAULT_BRANCH


class SyncConfigOut(BaseModel):
    remote: str | None
    enabled: bool
    auto: bool
    interval_seconds: int
    branch: str
    updated_at: str


class SyncStatusOut(BaseModel):
    status: str
    last_sync_at: str | None
    last_error: str | None
    conflict_paths: list[str]
    locked_refs: list[str]
    quarantined_refs: list[str]


class SyncRunIn(BaseModel):
    pull: bool = True
    push: bool = True


class SyncResolveIn(BaseModel):
    strategy: str = Field(pattern="^(ours|theirs|resolved)$")
    paths: list[str] = Field(default_factory=list)


class KeyPathIn(BaseModel):
    path: str


class KeyOpOut(BaseModel):
    path: str


class MachineOut(BaseModel):
    machine_id: str
    display_name: str
    platform: str | None
    os_version: str | None
    coffer_version: str | None
    last_sync_at: str | None
    is_local: bool


class MachinesOut(BaseModel):
    machines: list[MachineOut]


class MachineRenameIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def _strip_and_require_visible(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("display_name must not be blank")
        return stripped


def _config_out(c: SyncConfig) -> SyncConfigOut:
    return SyncConfigOut(
        remote=c.remote,
        enabled=c.enabled,
        auto=c.auto,
        interval_seconds=c.interval_seconds,
        branch=c.branch,
        updated_at=c.updated_at.isoformat(),
    )


def _status_out(s: SyncState) -> SyncStatusOut:
    return SyncStatusOut(
        status=s.status.value,
        last_sync_at=s.last_sync_at.isoformat() if s.last_sync_at else None,
        last_error=s.last_error,
        conflict_paths=s.conflict_paths,
        locked_refs=s.locked_refs,
        quarantined_refs=s.quarantined_refs,
    )


# --- routes ----------------------------------------------------------------


@router.get("/config", response_model=SyncConfigOut)
async def get_config() -> SyncConfigOut:
    return _config_out(await get_sync_service().get_config())


@router.put("/config", response_model=SyncConfigOut)
async def put_config(body: SyncConfigIn, actor: str = Depends(get_actor)) -> SyncConfigOut:
    saved = await get_sync_service().update_config(
        remote=body.remote,
        enabled=body.enabled,
        auto=body.auto,
        interval_seconds=body.interval_seconds,
        branch=body.branch,
        actor=actor,
    )
    return _config_out(saved)


@router.get("/status", response_model=SyncStatusOut)
async def get_status() -> SyncStatusOut:
    return _status_out(await get_sync_service().status())


@router.post("/run", response_model=SyncStatusOut)
async def run_sync(body: SyncRunIn | None = None) -> SyncStatusOut:
    body = body or SyncRunIn()
    return _status_out(await get_sync_service().run(pull=body.pull, push=body.push))


@router.post("/resolve", response_model=SyncStatusOut)
async def resolve_sync(body: SyncResolveIn) -> SyncStatusOut:
    return _status_out(await get_sync_service().resolve(body.strategy, body.paths))


@router.get("/machines", response_model=MachinesOut)
async def list_machines() -> MachinesOut:
    identity, entries = await get_sync_service().list_machines()
    return MachinesOut(
        machines=[
            MachineOut(
                machine_id=e.machine_id,
                display_name=e.display_name,
                platform=e.platform,
                os_version=e.os_version,
                coffer_version=e.coffer_version,
                last_sync_at=e.last_sync_at.isoformat() if e.last_sync_at else None,
                is_local=e.machine_id == identity.machine_id,
            )
            for e in entries
        ]
    )


@router.put("/machine", response_model=MachineOut)
async def rename_machine(body: MachineRenameIn, actor: str = Depends(get_actor)) -> MachineOut:
    service = get_sync_service()
    await service.rename_machine(body.display_name, actor=actor)
    identity, entries = await service.list_machines()
    own = next(e for e in entries if e.machine_id == identity.machine_id)
    return MachineOut(
        machine_id=own.machine_id,
        display_name=own.display_name,
        platform=own.platform,
        os_version=own.os_version,
        coffer_version=own.coffer_version,
        last_sync_at=own.last_sync_at.isoformat() if own.last_sync_at else None,
        is_local=True,
    )


@router.post("/key/export", response_model=KeyOpOut)
async def export_key(body: KeyPathIn) -> KeyOpOut:
    return KeyOpOut(path=await get_sync_service().export_key(body.path))


@router.post("/key/import", response_model=SyncStatusOut)
async def import_key(body: KeyPathIn) -> SyncStatusOut:
    return _status_out(await get_sync_service().import_key(body.path))
