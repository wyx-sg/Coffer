"""GET /api/v1/chat/conversations/{id}/attachments/{attachment_id} — the bytes
of a file attached to a message, for the thread's thumbnail (spec chat "Show a
message's attachments in the thread")."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from coffer.application.chat.attachments import ChatAttachmentService
from coffer.application.chat.service import ChatService
from coffer.domain.chat.errors import AttachmentUnavailable
from coffer.domain.chat.message import AttachmentBlock
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.dependencies import get_attachment_service, get_chat_service

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    dependencies=[Depends(require_token)],
)


#: The image types a thread thumbnail may show inline (what an upload's bytes
#: can be sniffed as); anything else is served as a download.
_INLINE_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})


@router.get("/conversations/{id}/attachments/{attachment_id}")
async def get_attachment_bytes(
    id: str,
    attachment_id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    attachments: ChatAttachmentService = Depends(get_attachment_service),  # noqa: B008
) -> FileResponse:
    """The bytes of a file attached to one of this conversation's messages, for
    the thread's thumbnail (spec chat "Show a message's attachments in the
    thread"). Only an id a message of THIS conversation references resolves, and
    only through the media store, so no client-supplied path is ever read; an
    unknown id, another conversation's file or a pruned one is 404."""
    messages = await svc.list_messages(id)
    referenced = any(
        isinstance(block, AttachmentBlock) and block.id == attachment_id
        for message in messages
        for block in message.content
    )
    stored = await attachments.stored(attachment_id) if referenced else None
    if stored is None:
        raise AttachmentUnavailable(attachment_id)
    return FileResponse(
        stored.path,
        media_type=stored.mime,
        filename=stored.filename,
        content_disposition_type="inline" if stored.mime in _INLINE_IMAGE_MIMES else "attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )
