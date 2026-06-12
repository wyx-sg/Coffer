"""/api/v1/chat/conversations/{id}/messages — SSE turn endpoint.

POST validates the body, calls TurnOrchestrator.start_turn(), and:
- On pre-stream errors (TurnInProgress / NoModelConfigured / ConversationNotFound)
  returns a JSON error envelope (409 / 409 / 404) — NOT an SSE stream.
- On success returns an EventSourceResponse that drains the asyncio.Queue and
  emits one SSE event per AgentEvent; the stream closes on the None sentinel.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from coffer.application.chat.ports import ApprovalDecision
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.domain.chat.events import AgentEvent
from coffer.domain.errors import ConversationNotFound, NoModelConfigured, TurnInProgress
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.schemas import ApprovalSubmit, SendMessageRequest
from coffer.surfaces.http.dependencies import get_chat_service, get_turn_orchestrator

_logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    dependencies=[Depends(require_token)],
)


def _error_json(code: str, message: str, http_status: int) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"error": {"code": code, "message": message, "details": {}}},
    )


@router.post(
    "/conversations/{id}/messages",
    response_class=Response,
)
async def send_message(
    id: str,
    body: SendMessageRequest,
    orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),  # noqa: B008
) -> Any:
    """Append user message and stream the agent turn as SSE.

    Pre-stream errors are returned as JSON (not SSE):
    - 404 ConversationNotFound
    - 409 TurnInProgress
    - 409 NoModelConfigured

    On success the response content-type is ``text/event-stream``; the stream
    closes after the ``None`` sentinel is received from the turn queue.
    """
    try:
        queue: asyncio.Queue[AgentEvent | None] = await orchestrator.start_turn(id, body.text)
    except ConversationNotFound as exc:
        return _error_json(exc.code, str(exc), 404)
    except TurnInProgress as exc:
        return _error_json(exc.code, str(exc), 409)
    except NoModelConfigured as exc:
        return _error_json(exc.code, str(exc), 409)

    async def _event_stream() -> AsyncIterator[dict[str, Any]]:
        try:
            while True:
                event: AgentEvent | None = await queue.get()
                if event is None:
                    # End-of-stream sentinel — close the stream.
                    return
                data = json.dumps(dataclasses.asdict(event))
                yield {"event": event.type, "data": data}
        except asyncio.CancelledError:
            # Client disconnected; the turn task continues running (research.md §6).
            _logger.debug("SSE client disconnected for conversation %s", id)
            raise

    return EventSourceResponse(_event_stream())


@router.post(
    "/conversations/{id}/approvals",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def submit_approval(
    id: str,
    body: ApprovalSubmit,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),  # noqa: B008
) -> Response:
    """Deliver an allow/deny decision to a turn paused on an approval request.

    404 ``ConversationNotFound`` when the conversation does not exist;
    409 ``ApprovalNotFound`` when no pending request matches ``request_id``.
    """
    await svc.get_conversation(id)  # raises ConversationNotFound -> 404
    orchestrator.submit_approval(
        id,
        body.request_id,
        ApprovalDecision(behavior=body.behavior, message=body.message),
    )  # raises ApprovalNotFound -> 409
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    """Stop the conversation's in-flight turn, keeping its partial output.

    404 ``ConversationNotFound`` when the conversation does not exist; a no-op
    when no turn is in flight.
    """
    await svc.get_conversation(id)  # raises ConversationNotFound -> 404
    orchestrator.interrupt_turn(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
