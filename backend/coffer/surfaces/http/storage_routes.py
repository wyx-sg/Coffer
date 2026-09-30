"""``/api/v1/storage`` — what Coffer keeps on this machine, and clearing the rebuildable cache.

Spec daemon "Report what Coffer stores and clear the rebuildable cache", read
by Settings > Data. Measuring and clearing are in
``infrastructure/storage_usage.py``; this module only picks the sync working
tree (the vault, when sync is set up), refuses a clear while a memory pass is
rewriting the tree, and records the clear.
"""

from __future__ import annotations

import asyncio
import pathlib

from fastapi import APIRouter, Depends

from coffer.application.audit_service import AuditService
from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import UpkeepAlreadyRunning
from coffer.domain.sync.backup import DEFAULT_WORKTREE
from coffer.infrastructure import storage_usage
from coffer.surfaces.http import sync_routes
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.daemon_schemas import (
    CacheClearOut,
    CacheUsageOut,
    HistoryUsageOut,
    LocalContentUsageOut,
    StorageSummaryOut,
    VaultUsageOut,
)
from coffer.surfaces.http.dependencies import get_actor, get_audit_service

router = APIRouter(prefix="/api/v1/storage", tags=["daemon"], dependencies=[Depends(require_token)])


async def _sync_worktree() -> pathlib.Path:
    """The configured sync tree, else the default one (which may not exist)."""
    worktree = DEFAULT_WORKTREE
    try:
        remote = await sync_routes.get_sync_service().get_remote()
    except Exception:
        remote = None
    if remote is not None:
        worktree = remote.worktree_path
    return pathlib.Path(worktree).expanduser()


@router.get("", response_model=StorageSummaryOut)
async def storage_summary() -> StorageSummaryOut:
    usage = await asyncio.to_thread(storage_usage.measure, await _sync_worktree())
    return StorageSummaryOut(
        vault=VaultUsageOut(
            path=usage.vault.path, bytes=usage.vault.bytes, versions=usage.vault.versions
        ),
        local_content=LocalContentUsageOut(
            folder=usage.local_content.folder,
            locations=usage.local_content.locations,
            bytes=usage.local_content.bytes,
        ),
        history=HistoryUsageOut(path=usage.history.path, bytes=usage.history.bytes),
        cache=CacheUsageOut(bytes=usage.cache_bytes),
    )


@router.post("/cache/clear", response_model=CacheClearOut)
async def clear_cache(
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> CacheClearOut:
    """Delete the memory tree's files and the transcript summary cache.

    Partitions keep their rows; the next memory update rebuilds their folders
    from the agents' own memory. Refused (409) while a memory pass is running,
    because that pass is writing into the tree being cleared.
    """
    busy = next((run for run in UPKEEP_RUNS.list_running() if run.kind == "memory"), None)
    if busy is not None:
        raise UpkeepAlreadyRunning(busy.kind, busy.name)
    freed = await asyncio.to_thread(storage_usage.clear_cache)
    await audit.record(
        AuditEventType.STORAGE_CACHE_CLEARED.value,
        actor=actor,
        details={"cleared_bytes": freed},
    )
    return CacheClearOut(cleared_bytes=freed)
