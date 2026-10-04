"""/api/v1/chat/conversations — the Conversations page's REST surface.

Coffer lists the conversations its channels run (an index: title, agent,
channel, directory, native session id); the text of a conversation lives in the
agent's own session. Domain errors propagate to the app-wide handler in
``surfaces/http/errors.py``, which renders the standard ``{error, message}``
envelope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from coffer.application.chat.conversation_repo import Narrowing
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
    ConversationListOut,
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


@router.get("/conversations", response_model=ConversationListOut)
async def list_conversations(
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(
        default=None,
        description=(
            "The previous page's next_cursor. Bound to the filters it was issued "
            "for; any other value is 400 CURSOR_INVALID."
        ),
    ),
    q: str | None = Query(
        default=None,
        max_length=200,
        description=(
            "Title or working directory contains this text (case-insensitive); "
            "a cursor is bound to it."
        ),
    ),
    source: str | None = Query(
        default=None,
        max_length=2000,
        description=(
            "Comma-separated channel uids. Absent or empty is every channel; a "
            "cursor is bound to it."
        ),
    ),
    agent: str | None = Query(
        default=None,
        max_length=2000,
        description=(
            "Comma-separated agent keys (e.g. `claude_code,codex`). Absent or empty "
            "is every agent; a cursor is bound to it."
        ),
    ),
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    places: ChannelPlacesPort | None = Depends(get_channel_places),  # noqa: B008
) -> ConversationListOut:
    """Channel conversations, newest activity first (id breaks ties), paged by
    cursor; ``q`` filters by title or directory, ``source`` and ``agent`` by
    channel and by which agent it runs (all three also narrow ``total``)."""
    narrow = Narrowing.parse(source, agent)
    page = await svc.page_conversations(limit=limit, cursor=cursor, q=q, narrow=narrow)
    extras = await conversation_extras(page.items, resources, places)
    return ConversationListOut(
        conversations=[_conv_out(c, extras) for c in page.items],
        next_cursor=page.next_cursor,
        total=await svc.count_conversations(q=q, narrow=narrow),
    )


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
