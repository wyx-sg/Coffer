"""/api/v1/fs/* — read-only local filesystem browsing (spec 004 FR-024).

Backs the web folder picker for choosing an agent's skill directory: a browser
can't read absolute filesystem paths, but the loopback daemon can. Lists
subdirectories only — never file contents.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.fs.browse_service import FsBrowseService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_fs_browse_service

router = APIRouter(
    prefix="/api/v1/fs",
    tags=["fs"],
    dependencies=[Depends(require_token)],
)


class FsEntryOut(BaseModel):
    name: str
    path: str


class FsBrowseOut(BaseModel):
    path: str
    parent: str | None
    entries: list[FsEntryOut]


@router.get("/browse", response_model=FsBrowseOut)
async def browse(
    path: str | None = None,
    svc: FsBrowseService = Depends(get_fs_browse_service),  # noqa: B008
) -> FsBrowseOut:
    """List the immediate subdirectories of `path` (defaults to the home dir)."""
    # to_thread: browse() does blocking resolve()/scandir() on a caller-supplied
    # path that could be a slow network mount — keep it off the event loop.
    result = await asyncio.to_thread(svc.browse, path)
    return FsBrowseOut(
        path=result.path,
        parent=result.parent,
        entries=[FsEntryOut(name=e.name, path=e.path) for e in result.entries],
    )
