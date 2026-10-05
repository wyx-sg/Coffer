"""/api/v1/chat/conversations — the Conversations page's REST surface.

Coffer indexes the conversations its channels run (title, agent, channel,
directory, native session id); they are listed with every agent's sessions
(``GET /api/v1/agent-sessions``). This surface reads, renames and deletes one
conversation. The text of a conversation lives in the agent's own session.
Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``,
which renders the standard ``{error, message}`` envelope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from coffer.application.chat.ports import ChannelPlacesPort
from coffer.application.chat.questions import needs_you
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.chat.turn_state import is_running
from coffer.application.resource_service import ResourceService
from coffer.domain.chat.conversation import Conversation
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.conversation_views import (
    Extras,
    channel_binding,
    conversation_extras,
)
from coffer.surfaces.http.chat.dependencies import (
    get_channel_places,
    get_chat_service,
    get_turn_orchestrator,
)
from coffer.surfaces.http.chat.schemas import (
    ConversationOut,
    ConversationPatch,
)
from coffer.surfaces.http.dependencies import get_resource_service

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    dependencies=[Depends(require_token)],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _conv_out(conv: Conversation, extras: Extras) -> ConversationOut:
    binding = channel_binding(conv, extras)
    return ConversationOut(
        id=conv.id,
        agent_key=conv.agent_key,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        channel_binding=binding,
        cwd=conv.agent_config.cwd,
        session_id=conv.agent_config.session_id,
        running=is_running(conv.id),
        needs_you=needs_you(conv.id),
    )


async def _one_out(
    conv: Conversation,
    resources: ResourceService,
    places_port: ChannelPlacesPort | None,
) -> ConversationOut:
    return _conv_out(conv, await conversation_extras([conv], resources, places_port))


# ---------------------------------------------------------------------------
# Conversation routes
# ---------------------------------------------------------------------------


@router.get("/conversations/{id}", response_model=ConversationOut)
async def get_conversation(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    places: ChannelPlacesPort | None = Depends(get_channel_places),  # noqa: B008
) -> ConversationOut:
    """Get a single conversation by id.  Returns 404 if not found."""
    return await _one_out(await svc.get_conversation(id), resources, places)


@router.patch("/conversations/{id}", response_model=ConversationOut)
async def update_conversation(
    id: str,
    body: ConversationPatch,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    places: ChannelPlacesPort | None = Depends(get_channel_places),  # noqa: B008
) -> ConversationOut:
    """Rename a conversation through its agent, then in the index.

    A body that names no ``title`` changes nothing and returns the conversation
    as it stands.
    """
    if body.title is not None:
        conv = await svc.retitle_conversation(id, new_title=body.title)
    else:
        conv = await svc.get_conversation(id)
    return await _one_out(conv, resources, places)


@router.delete(
    "/conversations/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_conversation(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),  # noqa: B008
) -> Response:
    """Delete a conversation through its agent, then its index row.

    Any in-flight turn for this conversation is cancelled (and discarded)
    before deletion so the background task does not keep running after the row
    is gone. An agent that refuses leaves the index row in place.
    """
    await svc.remove_conversation(id, cancel_turn_fn=orchestrator.cancel_turn)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
