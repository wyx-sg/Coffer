"""/api/v1/fs/* — local filesystem browse + open/reveal (spec 004 FR-024/FR-039).

Backs the web folder picker (browse) and the read-only file viewers' open/reveal
actions. A browser can't read absolute paths or reach the OS, but the loopback
daemon — always on the user's own machine — can (ADR-033). Browse lists
subdirectories only, never file contents; open/reveal act on an existing
absolute path and create nothing.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field

from coffer.application.fs.browse_service import FsBrowseService
from coffer.application.fs.editor_service import EditorDetectService
from coffer.application.fs.open_service import FsOpenService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_fs_browse_service

router = APIRouter(
    prefix="/api/v1/fs",
    tags=["fs"],
    dependencies=[Depends(require_token)],
)


def get_fs_open_service() -> FsOpenService:
    """FastAPI Depends() target — stateless, built per-request (like browse)."""
    return FsOpenService()


class FsEntryOut(BaseModel):
    name: str
    path: str


class FsBrowseOut(BaseModel):
    path: str
    parent: str | None
    entries: list[FsEntryOut]


class FsOpenRequest(BaseModel):
    # `with` is the preferred-editor preference; it's a Python keyword, so the
    # attribute is `app` with a wire alias.
    model_config = ConfigDict(populate_by_name=True)

    path: str
    app: str | None = Field(default=None, alias="with")


class FsRevealRequest(BaseModel):
    path: str


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


@router.post("/open", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def open_path(
    body: FsOpenRequest,
    svc: FsOpenService = Depends(get_fs_open_service),  # noqa: B008
) -> Response:
    """Open `path` in the preferred editor (`with`) or the OS default app."""
    await asyncio.to_thread(svc.open, body.path, body.app)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reveal", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def reveal_path(
    body: FsRevealRequest,
    svc: FsOpenService = Depends(get_fs_open_service),  # noqa: B008
) -> Response:
    """Select / reveal `path` in the OS file manager."""
    await asyncio.to_thread(svc.reveal, body.path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Installed-editor detection (backs the preferred-editor picker, spec 002) ---


class EditorOptionOut(BaseModel):
    label: str
    value: str


class FsEditorsOut(BaseModel):
    editors: list[EditorOptionOut]


def get_editor_detect_service() -> EditorDetectService:
    """FastAPI Depends() target — stateless, built per-request."""
    return EditorDetectService()


@router.get("/editors", response_model=FsEditorsOut)
async def list_editors(
    svc: EditorDetectService = Depends(get_editor_detect_service),  # noqa: B008
) -> FsEditorsOut:
    """List GUI editors detected on this machine for the preferred-editor picker."""
    # to_thread: detection does blocking PATH lookups / app-bundle stat calls.
    editors = await asyncio.to_thread(svc.list_editors)
    return FsEditorsOut(editors=[EditorOptionOut(label=e.label, value=e.value) for e in editors])
