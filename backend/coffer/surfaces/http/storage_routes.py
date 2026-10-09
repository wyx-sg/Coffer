"""``/api/v1/storage`` — what Coffer keeps on this machine.

Spec daemon "Report what Coffer stores", read by Settings > Data. Measuring is
in ``infrastructure/storage_usage.py``.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from coffer.infrastructure import storage_usage
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.daemon_schemas import (
    HistoryUsageOut,
    LocalContentUsageOut,
    StorageSummaryOut,
    VaultUsageOut,
)

router = APIRouter(prefix="/api/v1/storage", tags=["daemon"], dependencies=[Depends(require_token)])


@router.get("", response_model=StorageSummaryOut)
async def storage_summary() -> StorageSummaryOut:
    usage = await asyncio.to_thread(storage_usage.measure)
    return StorageSummaryOut(
        vault=VaultUsageOut(
            path=usage.vault.path,
            bytes=usage.vault.bytes,
            versions=usage.vault.versions,
        ),
        local_content=LocalContentUsageOut(
            folder=usage.local_content.folder,
            locations=usage.local_content.locations,
            bytes=usage.local_content.bytes,
        ),
        history=HistoryUsageOut(path=usage.history.path, bytes=usage.history.bytes),
    )
