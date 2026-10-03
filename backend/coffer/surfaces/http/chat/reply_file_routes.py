"""GET /api/v1/chat/conversations/{id}/messages/{message_id}/changes[/diff] — what
one assistant reply changed in each file (spec chat "Record what each reply
changed in each file")."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from coffer.application.chat.service import ChatService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.dependencies import get_chat_service

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    dependencies=[Depends(require_token)],
)


class ReplyFileOut(BaseModel):
    """One file a reply changed: its added and removed line counts, and whether
    a diff can be opened (false for a file too large or not text)."""

    path: str
    added: int
    removed: int
    has_diff: bool


class ReplyFileListOut(BaseModel):
    """The files a reply changed, first-touched first; empty for a reply that
    changed none and for one recorded before files were."""

    files: list[ReplyFileOut]


class ReplyFileDiffOut(BaseModel):
    """One changed file's unified diff. ``diff`` is ``null`` when it is left out,
    and ``diff_omitted`` then says why: ``binary`` (not text) or ``too_large``
    (over 1 MB)."""

    path: str
    added: int
    removed: int
    diff: str | None
    diff_omitted: Literal["binary", "too_large"] | None


@router.get(
    "/conversations/{id}/messages/{message_id}/changes",
    response_model=ReplyFileListOut,
)
async def list_reply_files(
    id: str,
    message_id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ReplyFileListOut:
    """The files an assistant reply of the conversation changed, with added and
    removed line counts. An id that is not an assistant message of the
    conversation is ``MessageNotFound`` (404); a reply with no records lists
    none."""
    files = await svc.reply_files(id, message_id)
    return ReplyFileListOut(
        files=[
            ReplyFileOut(path=f.path, added=f.added, removed=f.removed, has_diff=f.has_diff)
            for f in files
        ]
    )


@router.get(
    "/conversations/{id}/messages/{message_id}/changes/diff",
    response_model=ReplyFileDiffOut,
)
async def get_reply_file_diff(
    id: str,
    message_id: str,
    path: str = Query(..., min_length=1),
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ReplyFileDiffOut:
    """One changed file's unified diff for that reply. ``MessageNotFound`` (404)
    for a message that is not an assistant reply of the conversation,
    ``ReplyFileNotFound`` (404) for a path the reply did not record."""
    f = await svc.reply_file(id, message_id, path)
    return ReplyFileDiffOut(
        path=f.path,
        added=f.added,
        removed=f.removed,
        diff=f.diff,
        diff_omitted=f.diff_omitted,
    )
