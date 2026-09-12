"""/api/v1/agents/{name}/native-memory — read-only native-memory listing.

Lists a coding agent's OWN native per-project memory stores (Claude Code's
``<config_dir>/projects/<slug>/memory``, Codex's global ``memories/MEMORY.md``
sliced by routed cwd). Coffer never writes them: the user opens or reveals the
directory from the agent detail page's Memory tab.

Agents with no native memory layout — and agents with no projects dir on disk —
return an empty list; a non-existent agent name returns 404 via the service's
agent lookup.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.workspace_dependencies import get_agent_native_memory_service

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


class NativeMemoryStoreOut(BaseModel):
    project: str
    path: str | None
    memory_dir: str
    item_count: int


class NativeMemoryListOut(BaseModel):
    items: list[NativeMemoryStoreOut]


@router.get("/{name}/native-memory", response_model=NativeMemoryListOut)
async def list_native_memory(
    name: str,
    svc: Any = Depends(get_agent_native_memory_service),  # noqa: B008
) -> NativeMemoryListOut:
    """The agent's own native memory stores, most populated first."""
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
