"""/api/v1/conversations/* — chat HTTP routes (spec 008-builtin-agent-chat).

Sending a message returns a Server-Sent Events stream of runtime events. All
pre-stream validation (404 / 409 / 422 / 503) happens while awaiting
``ChatService.send`` so it maps to the normal error envelope; only once a turn
is accepted do we start the ``text/event-stream`` response.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from coffer.application.chat.service import ChatService
from coffer.domain.chat.conversation import ConversationStatus
from coffer.domain.chat.runtime import event_payload
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.schemas import (
    ConfirmIn,
    ConversationDetailOut,
    ConversationListOut,
    ConversationOut,
    CreateConversationIn,
    RenameConversationIn,
    SendMessageIn,
    conversation_out,
    message_out,
)
from coffer.surfaces.http.dependencies import get_actor as _actor
from coffer.surfaces.http.dependencies import get_chat_service

router = APIRouter(
    prefix="/api/v1/conversations",
    tags=["conversations"],
    dependencies=[Depends(require_token)],
)


@router.get("", response_model=ConversationListOut)
async def list_conversations(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ConversationListOut:
    parsed = ConversationStatus(status_filter) if status_filter else None
    items = await svc.list_conversations(status=parsed, limit=limit, offset=offset)
    return ConversationListOut(items=[conversation_out(c) for c in items])


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: CreateConversationIn,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ConversationOut:
    conv = await svc.create_conversation(target_ref=body.target_ref, actor=actor)
    return conversation_out(conv)


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ConversationDetailOut:
    conv = await svc.get_conversation(conversation_id)
    msgs = await svc.get_messages(conversation_id)
    return ConversationDetailOut(
        conversation=conversation_out(conv),
        messages=[message_out(m) for m in msgs],
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: str,
    body: RenameConversationIn,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ConversationOut:
    return conversation_out(await svc.rename(conversation_id, body.title, actor=actor))


@router.post("/{conversation_id}/archive", response_model=ConversationOut)
async def archive_conversation(
    conversation_id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ConversationOut:
    return conversation_out(await svc.archive(conversation_id, actor=actor))


@router.post("/{conversation_id}/restore", response_model=ConversationOut)
async def restore_conversation(
    conversation_id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ConversationOut:
    return conversation_out(await svc.restore(conversation_id, actor=actor))


@router.delete(
    "/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete_conversation(
    conversation_id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await svc.delete(conversation_id, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{conversation_id}/messages", response_class=StreamingResponse)
async def send_message(
    conversation_id: str,
    body: SendMessageIn,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> StreamingResponse:
    # Pre-stream validation (404 / 409 / 422 / 503) raises here and maps to the
    # normal error envelope before any streaming body is committed.
    gen = await svc.send(conversation_id, body.text, actor=actor)

    async def event_stream() -> AsyncGenerator[str, None]:
        async for ev in gen:
            yield f"data: {json.dumps(event_payload(ev))}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{conversation_id}/confirm", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def confirm_tool(
    conversation_id: str,
    body: ConfirmIn,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> Response:
    await svc.resolve_confirmation(conversation_id, body.request_id, body.approve)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{conversation_id}/stop", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def stop_turn(
    conversation_id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> Response:
    await svc.stop(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
