"""/api/v1/chat/conversations/{id}/... — turn messages, live events, queue.

Live mirror + pending queue (ADR chat-single-owner-live-mirror):
- ``POST .../messages`` is **fire-and-return**: it starts or enqueues a turn and
  returns ``202 {queued}``; it is no longer the event stream.
- ``POST .../messages/{message_id}/resend`` sends a persisted user message
  again, attachments included (the page's Retry).
- ``GET .../events`` is the SSE subscription any client attaches to; it replays
  the in-flight turn then streams live, and stays open across turns.
- ``PUT .../pending`` replaces the pending queue (resume / drop / reorder).
- ``POST .../interrupt`` stops the in-flight turn and pauses the queue.

Domain errors propagate to the app-wide handler (``surfaces/http/errors.py``),
which renders the ``{error: {code, message, details}}`` envelope with the mapped
status (e.g. ``ConversationNotFound`` → 404).
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sse_starlette.sse import EventSourceResponse

from coffer.application.chat.attachments import ChatAttachmentService
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.domain.chat.events import AgentEvent
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.dependencies import (
    get_attachment_service,
    get_chat_service,
    get_turn_orchestrator,
)
from coffer.surfaces.http.chat.schemas import (
    PendingQueueIn,
    PendingQueueOut,
    SendMessageAck,
    SendMessageRequest,
)

_logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    dependencies=[Depends(require_token)],
)


@router.post(
    "/conversations/{id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SendMessageAck,
)
async def send_message(
    id: str,
    body: SendMessageRequest,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),  # noqa: B008
    attachments_svc: ChatAttachmentService = Depends(get_attachment_service),  # noqa: B008
) -> SendMessageAck:
    """Start a turn for the message, or enqueue it behind the in-flight one.

    Fire-and-return (ADR chat-single-owner-live-mirror): the composer never locks
    — a message sent during a turn is queued, not rejected. Turn events are
    consumed via ``GET .../events``.
    ``ConversationNotFound`` propagates to the global handler as 404.

    ``attachment_ids`` resolve to the uploaded files, which the orchestrator
    persists as references after the text exactly as it does a channel's media
    (spec chat "Send uploaded files with a web message"); an id naming no
    upload is ``AttachmentNotFound`` (422) and nothing is persisted or queued.
    """
    await svc.get_conversation(id)  # a missing path answers before a bad body
    attachments = await attachments_svc.resolve(body.attachment_ids)
    text = attachments_svc.message_text(body.text, attachments)
    queued = await orchestrator.enqueue_message(
        id,
        text,
        attachments=attachments,
        title_hint=attachments_svc.title_hint(body.text, attachments),
    )
    return SendMessageAck(queued=queued)


@router.post(
    "/conversations/{id}/messages/{message_id}/resend",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SendMessageAck,
)
async def resend_message(
    id: str,
    message_id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),  # noqa: B008
    attachments_svc: ChatAttachmentService = Depends(get_attachment_service),  # noqa: B008
) -> SendMessageAck:
    """Send one of the conversation's user messages again, attachments included.

    This is the page's Retry after a failed turn (spec chat "Show a failed turn
    as one inline banner with Retry"). The daemon rebuilds the message from its
    persisted row, so the retry carries the original's text AND its attachment
    references, whether they came from the web composer or a channel; a new
    user row is persisted exactly as a send would. A referenced file the media
    sweep has since deleted is ``AttachmentExpired`` (410) and nothing is
    persisted or queued; an id naming no user message of the conversation is
    ``MessageNotFound`` (404).
    """
    message = await svc.get_user_message(id, message_id)
    text, attachments = await attachments_svc.reattach(message)
    queued = await orchestrator.enqueue_message(
        id, attachments_svc.message_text(text, attachments), attachments=attachments
    )
    return SendMessageAck(queued=queued)


@router.get("/conversations/{id}/events", response_class=EventSourceResponse)
async def subscribe_events(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),  # noqa: B008
) -> EventSourceResponse:
    """Subscribe to the conversation's live turn events (SSE, ADR chat-single-owner-live-mirror).

    On attach, the in-flight turn's events so far are replayed (and the current
    pending-queue snapshot), then events stream live; when idle the connection is
    held open and the next turn — from any surface — is streamed. 404 when the
    conversation does not exist. The stream ends on the ``None`` sentinel
    (conversation deleted) or when the client disconnects.
    """
    await svc.get_conversation(id)  # raises ConversationNotFound -> 404
    queue = orchestrator.subscribe(id)

    async def _event_stream() -> AsyncIterator[dict[str, Any]]:
        try:
            while True:
                event: AgentEvent | None = await queue.get()
                if event is None:
                    return  # bus closed (conversation deleted)
                yield {"event": event.type, "data": json.dumps(dataclasses.asdict(event))}
        finally:
            # Client disconnect or stream end — detach this subscriber. The turn
            # task keeps running for other subscribers (ADR chat-single-owner-live-mirror).
            orchestrator.unsubscribe(id, queue)
            _logger.debug("events subscriber detached for conversation %s", id)

    return EventSourceResponse(_event_stream())


@router.put("/conversations/{id}/pending", response_model=PendingQueueOut)
async def set_pending(
    id: str,
    body: PendingQueueIn,
    orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),  # noqa: B008
) -> PendingQueueOut:
    """Replace the conversation's pending message queue (resume / drop / reorder).

    Unpauses the queue and starts the next turn when none is in flight; broadcasts
    ``queue_changed``. 404 when the conversation does not exist.
    """
    pending = await orchestrator.set_pending(id, body.pending)
    return PendingQueueOut(pending=pending)


@router.post(
    "/conversations/{id}/interrupt",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def interrupt_turn(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),  # noqa: B008
) -> Response:
    """Stop the conversation's in-flight turn (keeping its partial output) and
    pause the pending queue.

    404 ``ConversationNotFound`` when the conversation does not exist; a no-op
    when no turn is in flight.
    """
    await svc.get_conversation(id)  # raises ConversationNotFound -> 404
    orchestrator.interrupt_turn(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
