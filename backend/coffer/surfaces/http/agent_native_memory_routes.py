"""/api/v1/agents/{name}/native-memory* — read-only native-memory surfaces.

Lists a coding agent's OWN native per-project memory stores (Claude Code's
``<config_dir>/projects/<slug>/memory``, Codex's global ``memories/MEMORY.md``
sliced by routed cwd), and opens one of them: its directory as a tree and one of
its files as text. Coffer never writes any of it — the store's page offers
open-in-editor / reveal so a change happens in the user's own editor, where the
user sees the file and owns the consequence.

A store IS a directory, which is why its page is a tree plus a preview rather
than a rendering of some interpretation of it: the reader sees the same bytes
the agent will. The ``dir`` a client names is checked against the layout before
anything is read, so this cannot become a general reader for the rest of the
agent's config dir; a directory that is not one of this agent's stores is 404,
the same answer as a store that has gone, so the difference cannot be used to
probe.

Agents with no native memory layout — and agents with no projects dir on disk —
return an empty list; a non-existent agent name returns 404 via the service's
agent lookup. Like every workspace listing (spec agent-registry FR-048), none of
these audits.
"""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.errors import error_response
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


class MemoryFileNodeOut(BaseModel):
    """One entry in a store's tree. ``path`` is relative to the store dir."""

    name: str
    path: str
    type: str  # "file" | "dir"
    size: int | None = None
    #: A directory whose descendants were clipped at the walk-depth bound.
    truncated: bool = False
    children: list[MemoryFileNodeOut] = Field(default_factory=list)


class MemoryFileTreeOut(BaseModel):
    root: MemoryFileNodeOut


class MemoryFileContentOut(BaseModel):
    """One file's contents. No fingerprint — this surface has no write."""

    path: str
    #: Absolute path on disk, so the viewer can offer open / reveal (spec
    #: agent-registry FR-047).
    abs_path: str
    content: str  # empty when ``binary``
    truncated: bool
    binary: bool
    size: int


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


@router.get("/{name}/native-memory/files", response_model=MemoryFileTreeOut)
async def list_native_memory_files(
    name: str,
    dir: str = Query(description="A memory_dir from the listing — this agent's store."),
    svc: Any = Depends(get_agent_native_memory_service),  # noqa: B008
) -> MemoryFileTreeOut:
    """One native-memory store's directory, as a read-only tree."""
    try:
        root = await svc.read_tree(name, dir)
    except ValueError:
        return error_response(  # type: ignore[return-value]
            "NOT_FOUND",
            "no such native memory store for this agent",
        )
    return MemoryFileTreeOut(root=_node_out(root))


@router.get("/{name}/native-memory/files/content", response_model=MemoryFileContentOut)
async def read_native_memory_file(
    name: str,
    dir: str = Query(description="A memory_dir from the listing — this agent's store."),
    path: str = Query(min_length=1, description="File path relative to the store directory."),
    svc: Any = Depends(get_agent_native_memory_service),  # noqa: B008
) -> MemoryFileContentOut:
    """Read one file inside a native-memory store, for the read-only preview."""
    try:
        content = await svc.read_file(name, dir, path)
    except (ValueError, FileNotFoundError):
        # One answer for "not this agent's store", "escapes the store" and "gone":
        # the caller is holding a stale or invented path either way, and telling
        # the three apart would say something about the filesystem.
        return error_response(  # type: ignore[return-value]
            "NOT_FOUND",
            "no such file in this agent's native memory store",
        )
    return MemoryFileContentOut(
        path=content.path,
        abs_path=str(pathlib.Path(dir) / content.path),
        content=content.content,
        truncated=content.truncated,
        binary=content.binary,
        size=content.size,
    )


def _node_out(node: Any) -> MemoryFileNodeOut:
    """Project a domain ``MemoryFileNode`` (and its children) onto the wire."""
    return MemoryFileNodeOut(
        name=node.name,
        path=node.path,
        type=node.type,
        size=node.size,
        truncated=node.truncated,
        children=[_node_out(child) for child in node.children],
    )
