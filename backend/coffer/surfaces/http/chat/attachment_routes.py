"""POST /api/v1/chat/attachments — the web composer's file upload.

A file attached on the Chat page is uploaded here first and sent later by the
opaque id this returns (``POST .../messages`` ``attachment_ids``), so a send
stays a small JSON body and the composer can show each file's progress and
failure on its own (ADR chat-attachment-uploads). The upload is not tied to a
conversation: a draft attaches files before its conversation exists.

Bounds are the application's (``ChatAttachmentService.upload``): over the
ceiling is ``ATTACHMENT_TOO_LARGE`` (413) naming the limit, a type no agent can
use is ``ATTACHMENT_TYPE_UNSUPPORTED`` (415). The multipart body is spooled to a
temporary file while it is parsed, so the ceiling is also enforced before any
parsing (:class:`_BoundedUploadRoute`): a request that declares a
``Content-Length`` over the ceiling plus a small allowance for the multipart
framing is refused with 413 unread, and the form is parsed with room for one
file and a handful of fields. A body sent without a declared length is parsed
and then refused by the same ceiling on the file's bytes.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from fastapi.routing import APIRoute

from coffer.application.chat.attachments import ChatAttachmentService
from coffer.domain.chat.attachment import MAX_ATTACHMENT_BYTES
from coffer.domain.chat.errors import AttachmentTooLarge
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.dependencies import get_attachment_service
from coffer.surfaces.http.chat.schemas import ChatAttachmentOut

#: Room for the multipart framing around the one file: boundaries, part
#: headers and the filename. Generous next to what a browser sends (~200 bytes).
MULTIPART_OVERHEAD_BYTES = 64 * 1024

#: The form holds one ``file`` part; a few fields of slack, never thousands.
_MAX_FORM_FILES = 1
_MAX_FORM_FIELDS = 4


class _BoundedUploadRoute(APIRoute):
    """Refuse an oversized upload before FastAPI spools its body: check the
    token (so an unauthenticated caller still gets 401, not 413), then the
    declared length, then parse the form with tight part limits. FastAPI's own
    ``request.form()`` afterwards returns the form parsed here."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            require_token(request.headers.get("x-coffer-token"))
            declared = request.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > (
                MAX_ATTACHMENT_BYTES + MULTIPART_OVERHEAD_BYTES
            ):
                raise AttachmentTooLarge(int(declared), MAX_ATTACHMENT_BYTES)
            await request.form(max_files=_MAX_FORM_FILES, max_fields=_MAX_FORM_FIELDS)
            return await handler(request)

        return bounded


router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    dependencies=[Depends(require_token)],
    route_class=_BoundedUploadRoute,
)


@router.post(
    "/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatAttachmentOut,
)
async def upload_attachment(
    file: UploadFile = File(...),  # noqa: B008
    svc: ChatAttachmentService = Depends(get_attachment_service),  # noqa: B008
) -> ChatAttachmentOut:
    """Store one file for a later send and return its id, name, type and size
    (spec chat "Upload a file for a web message"). The local path is never
    returned."""
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        size = file.size if file.size is not None else len(data)
        raise AttachmentTooLarge(size, MAX_ATTACHMENT_BYTES)
    stored = await svc.upload(filename=file.filename, declared_mime=file.content_type, data=data)
    return ChatAttachmentOut(
        id=stored.id, filename=stored.filename, mime=stored.mime, size=stored.size
    )
