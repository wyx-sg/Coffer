"""/api/v1/chat/conversations — conversation CRUD + message history routes.

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``,
which renders the standard ``{error, message}`` envelope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from coffer.application.chat.model_service import ModelService
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.message import (
    ContentBlock,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.schemas import (
    ChatAgentListOut,
    ChatAgentOut,
    ContentBlockOut,
    ConversationCreate,
    ConversationListOut,
    ConversationOut,
    ConversationPatch,
    MessageListOut,
    MessageOut,
)
from coffer.surfaces.http.dependencies import (
    get_agent_registry,
    get_chat_service,
    get_model_service,
    get_turn_orchestrator,
)

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    dependencies=[Depends(require_token)],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _conv_out(conv: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        agent_key=conv.agent_key,
        title=conv.title,
        model_id=conv.model_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


def _block_out(block: ContentBlock) -> ContentBlockOut:
    if isinstance(block, TextBlock):
        return ContentBlockOut(type="text", text=block.text)
    if isinstance(block, ToolUseBlock):
        return ContentBlockOut(
            type="tool_use",
            tool_use_id=block.tool_use_id,
            tool_name=block.tool_name,
            tool_input=block.tool_input,
        )
    if isinstance(block, ToolResultBlock):
        return ContentBlockOut(
            type="tool_result",
            tool_use_id=block.tool_use_id,
            tool_name=block.tool_name,
            output=block.output,
            error=block.error,
        )
    # Unreachable given the ContentBlock union, but keeps mypy happy.
    raise TypeError(f"unhandled ContentBlock type: {type(block)!r}")  # pragma: no cover


def _msg_out(msg: Message) -> MessageOut:
    return MessageOut(
        id=msg.id,
        conversation_id=msg.conversation_id,
        seq=msg.seq,
        role=str(msg.role),  # type: ignore[arg-type]
        content=[_block_out(b) for b in msg.content],
        status=msg.status,
        model_id=msg.model_id,
        prompt_tokens=msg.prompt_tokens,
        completion_tokens=msg.completion_tokens,
        created_at=msg.created_at,
    )


# ---------------------------------------------------------------------------
# Agent routes
# ---------------------------------------------------------------------------


@router.get("/agents", response_model=ChatAgentListOut)
async def list_agents(
    registry: AgentProviderRegistry = Depends(get_agent_registry),  # noqa: B008
) -> ChatAgentListOut:
    """List the agents the chat platform offers, each with an availability flag."""
    agents: list[ChatAgentOut] = []
    for entry in registry.entries():
        available = await entry.provider.availability()
        agents.append(
            ChatAgentOut(
                agent_key=entry.provider.agent_key,
                display_name=entry.display_name,
                available=available,
            )
        )
    return ChatAgentListOut(agents=agents)


# ---------------------------------------------------------------------------
# Conversation routes
# ---------------------------------------------------------------------------


@router.get("/conversations", response_model=ConversationListOut)
async def list_conversations(
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ConversationListOut:
    """List all conversations, newest first."""
    convs = await svc.list_conversations()
    return ConversationListOut(conversations=[_conv_out(c) for c in convs])


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    body: ConversationCreate | None = None,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ConversationOut:
    """Create a conversation for the named agent.

    ``agent_key`` defaults to the built-in agent; ``agent_config`` is validated
    by that agent. An unknown agent or an invalid config is rejected with 400.
    """
    agent_key = body.agent_key if body is not None else "builtin"
    agent_config = body.agent_config if body is not None else None
    conv = await svc.create_conversation(agent_key=agent_key, agent_config=agent_config)
    return _conv_out(conv)


@router.get("/conversations/{id}", response_model=ConversationOut)
async def get_conversation(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ConversationOut:
    """Get a single conversation by id.  Returns 404 if not found."""
    conv = await svc.get_conversation(id)
    return _conv_out(conv)


@router.patch("/conversations/{id}", response_model=ConversationOut)
async def update_conversation(
    id: str,
    body: ConversationPatch,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    model_svc: ModelService = Depends(get_model_service),  # noqa: B008
) -> ConversationOut:
    """Rename a conversation and/or change its model override."""
    # Validate EVERYTHING before writing anything, so a rejected request never
    # leaves a partially-applied PATCH (e.g. the rename committed but the
    # model change refused). A non-null model_id must reference a registered
    # model (ModelNotFound -> 404) rather than failing only at the next turn.
    set_model = "model_id" in body.model_fields_set
    if set_model and body.model_id is not None:
        await model_svc.get(body.model_id)  # raises ModelNotFound -> 404

    if body.title is not None:
        conv = await svc.rename_conversation(id, new_title=body.title)
    else:
        conv = await svc.get_conversation(id)

    if set_model:
        conv = await svc.set_conversation_model(id, model_id=body.model_id)

    return _conv_out(conv)


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
    """Delete a conversation and all its messages.

    Any in-flight turn for this conversation is cancelled (and discarded)
    before deletion so the background task does not keep running after the row
    is gone (FR-016 / FR-021).
    """
    await svc.delete_conversation(id, cancel_turn_fn=orchestrator.cancel_turn)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Message routes
# ---------------------------------------------------------------------------


@router.get("/conversations/{id}/messages", response_model=MessageListOut)
async def list_messages(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> MessageListOut:
    """Return message history for a conversation, ordered by seq ascending."""
    msgs = await svc.list_messages(id)
    return MessageListOut(messages=[_msg_out(m) for m in msgs])
