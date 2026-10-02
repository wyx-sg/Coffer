"""/api/v1/chat/conversations — conversation CRUD + message history routes.

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``,
which renders the standard ``{error, message}`` envelope.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from fastapi import APIRouter, Depends, Query, Response, status

from coffer.application.chat.ports import ChannelMirrorPort
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.chat.turn_state import is_running
from coffer.application.resource_service import ResourceService
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.message import (
    AttachmentBlock,
    ContentBlock,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from coffer.domain.chat.mirror import ChannelPlaceView, MirrorView
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.dependencies import (
    get_channel_mirror,
    get_chat_service,
    get_turn_orchestrator,
)
from coffer.surfaces.http.chat.schemas import (
    AgentConfigOut,
    AgentConfigPatch,
    ChannelBindingOut,
    ChannelMirrorOut,
    ChannelPlaceOut,
    ContentBlockOut,
    ConversationCreate,
    ConversationListOut,
    ConversationOut,
    ConversationPatch,
    MessageListOut,
    MessageOut,
    UndeliveredReplyOut,
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


@dataclass(frozen=True)
class _Channel:
    name: str
    #: The channel's type key (``seatalk`` / ``telegram``), or None if unset.
    platform: str | None


@dataclass(frozen=True)
class _Extras:
    """What a page of conversations is rendered with beyond its rows, read in a
    CONSTANT number of queries whatever the page size: the channels once, the
    places of the channel-bound ones once, the previews once. A read per row
    would be the N+1 the resource list was ordered to avoid."""

    channels: Mapping[str, _Channel]
    places: Mapping[str, ChannelPlaceView]
    previews: Mapping[str, str]


async def _extras(
    convs: Sequence[Conversation],
    svc: ChatService,
    resources: ResourceService,
    mirror: ChannelMirrorPort | None,
) -> _Extras:
    channels = {
        c.uid: _Channel(c.name, str(c.config.get("channel_type") or "") or None)
        for c in await resources.list(kind="channel")
    }
    bound = [c.id for c in convs if c.channel_uid is not None]
    places = await mirror.places(bound) if mirror is not None and bound else {}
    previews = await svc.previews([c.id for c in convs]) if convs else {}
    return _Extras(channels, places, previews)


def _place_out(view: ChannelPlaceView) -> ChannelPlaceOut:
    return ChannelPlaceOut(
        chat_kind=view.chat_kind,  # type: ignore[arg-type]
        thread=view.thread,
        parallel_mark=view.parallel_mark,
        chat_name=view.chat_name,
    )


def _mirror_out(view: MirrorView) -> ChannelMirrorOut:
    return ChannelMirrorOut(
        deliverable=view.deliverable,
        platform=view.platform,  # type: ignore[arg-type]
        target=view.target,
        reason=view.reason,
        undelivered=[
            UndeliveredReplyOut(kind=u.kind, text=u.text, created_at=u.created_at)  # type: ignore[arg-type]
            for u in view.undelivered
        ],
    )


def _conv_out(
    conv: Conversation,
    extras: _Extras,
    mirror: MirrorView | None = None,
) -> ConversationOut:
    # A conversation "has a channel binding" iff channel_uid is set
    # (ADR chat-single-owner-live-mirror). The row stores the channel's
    # IDENTITY so a renamed channel keeps its conversations; the NAME is
    # resolved here, where a human reads it.
    binding: ChannelBindingOut | None = None
    if conv.channel_uid is not None:
        channel = extras.channels.get(conv.channel_uid)
        place = extras.places.get(conv.id)
        binding = ChannelBindingOut(
            channel_uid=conv.channel_uid,
            channel=channel.name if channel is not None else None,
            chat_id=conv.peer_chat_id or "",
            platform=channel.platform if channel is not None else None,  # type: ignore[arg-type]
            place=_place_out(place) if place is not None else None,
            mirror=_mirror_out(mirror) if mirror is not None else None,
        )
    return ConversationOut(
        id=conv.id,
        agent_key=conv.agent_key,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        archived_at=conv.archived_at,
        channel_binding=binding,
        preview=extras.previews.get(conv.id),
        running=is_running(conv.id),
    )


async def _one_out(
    conv: Conversation,
    svc: ChatService,
    resources: ResourceService,
    mirror: ChannelMirrorPort | None,
    view: MirrorView | None = None,
) -> ConversationOut:
    return _conv_out(conv, await _extras([conv], svc, resources, mirror), view)


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
    if isinstance(block, AttachmentBlock):
        # Reference only — filename/mime for the chip; never the local path.
        return ContentBlockOut(type="attachment", filename=block.filename, mime=block.mime)
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
# Conversation routes
# ---------------------------------------------------------------------------


@router.get("/conversations", response_model=ConversationListOut)
async def list_conversations(
    archived: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(
        default=None,
        description=(
            "The previous page's next_cursor. Bound to the listing (active or "
            "archived) it was issued for; any other value is 400 CURSOR_INVALID."
        ),
    ),
    q: str | None = Query(
        default=None,
        max_length=200,
        description="Title contains this text (case-insensitive); a cursor is bound to it.",
    ),
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    mirror: ChannelMirrorPort | None = Depends(get_channel_mirror),  # noqa: B008
) -> ConversationListOut:
    """Conversations newest activity first (id breaks ties), paged by cursor;
    ``archived=true`` lists the archived ones, ``q`` filters by title."""
    page = await svc.page_conversations(archived=archived, limit=limit, cursor=cursor, q=q)
    extras = await _extras(page.items, svc, resources, mirror)
    return ConversationListOut(
        conversations=[_conv_out(c, extras) for c in page.items],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    body: ConversationCreate,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    mirror: ChannelMirrorPort | None = Depends(get_channel_mirror),  # noqa: B008
) -> ConversationOut:
    """Create a conversation for the named Coffer-managed agent.

    ``agent_key`` is required — chat has no built-in agent (ADR
    coffer-model-is-an-internal-engine); ``agent_config`` is validated by that
    agent. An unknown agent or an invalid config is rejected with 400.
    """
    conv = await svc.create_conversation(agent_key=body.agent_key, agent_config=body.agent_config)
    return await _one_out(conv, svc, resources, mirror)


@router.get("/conversations/{id}", response_model=ConversationOut)
async def get_conversation(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    mirror: ChannelMirrorPort | None = Depends(get_channel_mirror),  # noqa: B008
) -> ConversationOut:
    """Get a single conversation by id.  Returns 404 if not found.

    A conversation a channel drives also says where a reply typed here would go
    (``channel_binding.mirror``, spec chat "Mirror a web reply into the channel
    it came from") — read here only, so the list stays one query."""
    conv = await svc.get_conversation(id)
    view = None
    if conv.channel_uid is not None and mirror is not None:
        view = await mirror.describe(conv.id, conv.channel_uid)
    return await _one_out(conv, svc, resources, mirror, view)


@router.patch("/conversations/{id}", response_model=ConversationOut)
async def update_conversation(
    id: str,
    body: ConversationPatch,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    mirror: ChannelMirrorPort | None = Depends(get_channel_mirror),  # noqa: B008
) -> ConversationOut:
    """Rename a conversation.

    A body that names no ``title`` changes nothing and returns the conversation
    as it stands. The agent's own model is not set here — it lives in the
    conversation's agent_config (PATCH ``/conversations/{id}/agent-config``,
    ADR model-catalogue-read-from-the-agent).
    """
    if body.title is not None:
        conv = await svc.rename_conversation(id, new_title=body.title)
    else:
        conv = await svc.get_conversation(id)
    return await _one_out(conv, svc, resources, mirror)


@router.get("/conversations/{id}/agent-config", response_model=AgentConfigOut)
async def get_agent_config(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> AgentConfigOut:
    """Read a conversation's agent config (cwd, model, effort). 404 if not found.

    ``session_id`` is provider-internal and deliberately not surfaced.
    """
    cfg = await svc.get_agent_config(id)  # raises ConversationNotFound -> 404
    return AgentConfigOut(cwd=cfg.cwd, model=cfg.model, effort=cfg.effort)


@router.patch("/conversations/{id}/agent-config", response_model=AgentConfigOut)
async def set_agent_config(
    id: str,
    body: AgentConfigPatch,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> AgentConfigOut:
    """Set a managed agent's own model and effort for a conversation (ADR
    coffer-model-is-an-internal-engine → ADR model-catalogue-read-from-the-agent).

    Mirrors the channel ``/model`` command: read-then-``replace`` so ``cwd`` and
    ``session_id`` are preserved, and a body that mentions only one of the two
    leaves the other where it was. An empty/whitespace ``model`` clears the
    override (the conversation then inherits the active provider profile's
    projected default); an empty/whitespace ``effort`` clears it (the agent then
    runs at whatever its own config says).
    """
    cfg = await svc.get_agent_config(id)  # raises ConversationNotFound -> 404
    fields: dict[str, str | None] = {}
    if "model" in body.model_fields_set:
        fields["model"] = (body.model or "").strip() or None
    if "effort" in body.model_fields_set:
        fields["effort"] = (body.effort or "").strip() or None
    if fields:
        cfg = replace(cfg, **fields)
        await svc.set_agent_config(id, cfg)
    return AgentConfigOut(cwd=cfg.cwd, model=cfg.model, effort=cfg.effort)


@router.post("/conversations/{id}/archive", response_model=ConversationOut)
async def archive_conversation(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    mirror: ChannelMirrorPort | None = Depends(get_channel_mirror),  # noqa: B008
) -> ConversationOut:
    """Archive a conversation — hidden from the default list, still restorable."""
    conv = await svc.archive_conversation(id)
    return await _one_out(conv, svc, resources, mirror)


@router.post("/conversations/{id}/unarchive", response_model=ConversationOut)
async def unarchive_conversation(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    mirror: ChannelMirrorPort | None = Depends(get_channel_mirror),  # noqa: B008
) -> ConversationOut:
    """Restore an archived conversation back into the active list."""
    conv = await svc.unarchive_conversation(id)
    return await _one_out(conv, svc, resources, mirror)


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
    is gone (spec chat "Create, rename, archive, unarchive and delete
    conversations").
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
