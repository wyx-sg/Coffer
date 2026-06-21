"""/api/v1/chat/conversations — conversation CRUD + message history routes.

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``,
which renders the standard ``{error, message}`` envelope.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends, Response, status

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
    AgentConfigOut,
    AgentConfigPatch,
    ChannelBindingOut,
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
    # A conversation "has a channel binding" iff channel_name is set (ADR-031).
    binding: ChannelBindingOut | None = None
    if conv.channel_name is not None:
        binding = ChannelBindingOut(
            channel=conv.channel_name,
            chat_id=conv.peer_chat_id or "",
        )
    return ConversationOut(
        id=conv.id,
        agent_key=conv.agent_key,
        title=conv.title,
        model_id=conv.model_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        archived_at=conv.archived_at,
        channel_binding=binding,
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
    archived: bool = False,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ConversationListOut:
    """List conversations, newest first. ``?archived=true`` returns the archived
    threads; the default lists active ones only."""
    convs = await svc.list_conversations(archived=archived)
    return ConversationListOut(conversations=[_conv_out(c) for c in convs])


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    body: ConversationCreate,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ConversationOut:
    """Create a conversation for the named Coffer-managed agent.

    ``agent_key`` is required (chat has no built-in agent since ADR-024);
    ``agent_config`` is validated by that agent. An unknown agent or an invalid
    config is rejected with 400.
    """
    conv = await svc.create_conversation(agent_key=body.agent_key, agent_config=body.agent_config)
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
) -> ConversationOut:
    """Rename a conversation and/or change its model override.

    ``model_id`` is a vestigial per-conversation override column (the managed
    agent's own model lives in its agent_config, ADR-032); it is persisted as
    given without registry validation.
    """
    set_model = "model_id" in body.model_fields_set

    if body.title is not None:
        conv = await svc.rename_conversation(id, new_title=body.title)
    else:
        conv = await svc.get_conversation(id)

    if set_model:
        conv = await svc.set_conversation_model(id, model_id=body.model_id)

    return _conv_out(conv)


@router.get("/conversations/{id}/agent-config", response_model=AgentConfigOut)
async def get_agent_config(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> AgentConfigOut:
    """Read a conversation's agent config (cwd, model). 404 if not found.

    ``session_id`` is provider-internal and deliberately not surfaced.
    """
    cfg = await svc.get_agent_config(id)  # raises ConversationNotFound -> 404
    return AgentConfigOut(cwd=cfg.cwd, model=cfg.model)


@router.patch("/conversations/{id}/agent-config", response_model=AgentConfigOut)
async def set_agent_config(
    id: str,
    body: AgentConfigPatch,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> AgentConfigOut:
    """Set a managed agent's own model for a conversation (ADR-024 → ADR-032).

    Mirrors the channel ``/model`` command: read-then-``replace(cfg, model=...)``
    so ``cwd`` and ``session_id`` are preserved. An empty/whitespace ``model``
    clears the override (the conversation then inherits the active provider
    profile's projected default). The registry ``model_id`` (PATCH
    /conversations/{id}) is unrelated and is not read by the managed-agent turn
    path.
    """
    cfg = await svc.get_agent_config(id)  # raises ConversationNotFound -> 404
    if "model" in body.model_fields_set:
        new_model = (body.model or "").strip() or None
        cfg = replace(cfg, model=new_model)
        await svc.set_agent_config(id, cfg)
    return AgentConfigOut(cwd=cfg.cwd, model=cfg.model)


@router.post("/conversations/{id}/archive", response_model=ConversationOut)
async def archive_conversation(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ConversationOut:
    """Archive a conversation — hidden from the default list, still restorable."""
    conv = await svc.archive_conversation(id)
    return _conv_out(conv)


@router.post("/conversations/{id}/unarchive", response_model=ConversationOut)
async def unarchive_conversation(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ConversationOut:
    """Restore an archived conversation back into the active list."""
    conv = await svc.unarchive_conversation(id)
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
