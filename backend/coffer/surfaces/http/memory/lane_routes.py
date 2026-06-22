"""Slice-7 four-lane read routes: journal / handoff / consolidation-log.

Registered on the shared ``memory`` router (imported from ``routes``) to keep
each module under the file-size budget. Each mirrors ``get_rules``:
``ensure_store`` for the global name, ``Depends(require_token)`` (router-level),
read-only, 200 with empty content for an empty store (never 404).
"""

from __future__ import annotations

from fastapi import Depends

from coffer.application.memory.scope import GLOBAL_STORE_NAME
from coffer.application.memory.service import MemoryService
from coffer.surfaces.http.dependencies import get_memory_service
from coffer.surfaces.http.memory.routes import router
from coffer.surfaces.http.memory.schemas import (
    ConsolidationLogOut,
    HandoffOut,
    HandoffSceneOut,
    JournalFileOut,
    JournalOut,
)


@router.get("/{name}/journal", response_model=JournalOut)
async def get_journal(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> JournalOut:
    """List the store's ``journal/<period>.md`` files, newest period first."""
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    files = await mem_svc.read_journal(store_name=name)
    return JournalOut(
        files=[
            JournalFileOut(period=f.period, text=f.text, path=f.path, folder_path=f.folder_path)
            for f in files
        ]
    )


@router.get("/{name}/handoff", response_model=HandoffOut)
async def get_handoff(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> HandoffOut:
    """List the store's per-branch ``handoff/<slug>.md`` scenes."""
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    scenes = await mem_svc.read_handoff_scenes(store_name=name)
    return HandoffOut(
        scenes=[
            HandoffSceneOut(
                branch=s.branch,
                text=s.text,
                updated_at=s.updated_at,
                path=s.path,
                folder_path=s.folder_path,
            )
            for s in scenes
        ]
    )


@router.get("/{name}/consolidation-log", response_model=ConsolidationLogOut)
async def get_consolidation_log(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> ConsolidationLogOut:
    """Read the store-root ``consolidation-log.md`` (``text=None`` when absent)."""
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    log = await mem_svc.read_consolidation_log(store_name=name)
    return ConsolidationLogOut(text=log.text, path=log.path, folder_path=log.folder_path)
