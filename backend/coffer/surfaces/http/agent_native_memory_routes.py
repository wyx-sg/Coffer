"""/api/v1/agents/{name}/native-memory routes (spec 004, FR-040/FR-041).

Read-only listing of a coding agent's OWN native per-project memory stores
(Claude Code's ``<config_dir>/projects/<slug>/memory``) plus a POST that ADOPTS
one such store into Coffer memory — parsing each fact file and writing it to the
project-scoped inbox, then running the internal organizer. Agents with no native
memory layout — and agents with no projects dir on disk — return an empty list;
a non-existent agent name returns 404 via the service's agent lookup.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_agent_memory_import_service,
    get_agent_native_memory_service,
)

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


# ---------- response schemas ----------


class NativeMemoryStoreOut(BaseModel):
    project: str
    path: str | None
    memory_dir: str
    item_count: int


class NativeMemoryListOut(BaseModel):
    items: list[NativeMemoryStoreOut]


class ImportRequest(BaseModel):
    memory_dir: str


class ImportResultOut(BaseModel):
    imported: int
    skipped: int
    store: str | None
    project_path: str | None
    organized: bool


# ---------- routes ----------


@router.get("/{name}/native-memory", response_model=NativeMemoryListOut)
async def list_native_memory(
    name: str,
    svc: Any = Depends(get_agent_native_memory_service),  # noqa: B008
) -> NativeMemoryListOut:
    stores = await svc.list_stores(name)
    return NativeMemoryListOut(
        items=[
            NativeMemoryStoreOut(
                project=s.project_label,
                path=s.project_path,
                memory_dir=s.memory_dir,
                item_count=s.item_count,
            )
            for s in stores
        ]
    )


@router.post("/{name}/native-memory/import", response_model=ImportResultOut)
async def import_native_memory(
    name: str,
    body: ImportRequest,
    svc: Any = Depends(get_agent_memory_import_service),  # noqa: B008
) -> ImportResultOut:
    """Adopt the native memory store at ``body.memory_dir`` into Coffer memory.

    Unknown agent → 404 (service's agent lookup). An unresolvable path or a
    non-git project yields a zero-import result, never an error — the inbox is
    never corrupted."""
    result = await svc.import_store(name=name, memory_dir=body.memory_dir)
    return ImportResultOut(
        imported=result.imported,
        skipped=result.skipped,
        store=result.store,
        project_path=result.project_path,
        organized=result.organized,
    )
