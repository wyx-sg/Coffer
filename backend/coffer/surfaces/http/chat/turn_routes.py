"""/api/v1/chat/conversations/{id}/interrupt — stop a conversation's turn.

Turns are started by the channels (and the Conversations page lists them); the
only turn control left on the web is stopping one — which the "continue in the
terminal" hand-over does first.

Domain errors propagate to the app-wide handler (``surfaces/http/errors.py``),
which renders the ``{error: {code, message, details}}`` envelope with the mapped
status (e.g. ``ConversationNotFound`` → 404).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.dependencies import get_chat_service, get_turn_orchestrator

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    dependencies=[Depends(require_token)],
)


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
    """Stop the conversation's in-flight turn and pause the pending queue.

    404 ``ConversationNotFound`` when the conversation does not exist; a no-op
    when no turn is in flight.
    """
    await svc.get_conversation(id)  # raises ConversationNotFound -> 404
    orchestrator.interrupt_turn(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
