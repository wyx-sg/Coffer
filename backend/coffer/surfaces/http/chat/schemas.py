"""Pydantic schemas matching the chat paths in specs/channels/contracts/api.openapi.yaml.

Every request/response body the web Chat page's REST + SSE surface serves is
modelled here. Field names, types, and nullability mirror the yaml exactly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class _ErrorDetail(BaseModel):
    """Inner object inside the error envelope."""

    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorOut(BaseModel):
    """Standard error envelope — matches the global handler in errors.py.

    Shape: {error: {code, message, details}}.
    """

    error: _ErrorDetail


# ---------------------------------------------------------------------------
# ContentBlock
# ---------------------------------------------------------------------------


class ContentBlockOut(BaseModel):
    """Wire representation of a ContentBlock (text | tool_use | tool_result |
    attachment). ``filename``/``mime`` describe an ``attachment`` reference; the
    local ``path`` is deliberately NOT surfaced (leak/security — FR-033)."""

    type: Literal["text", "tool_use", "tool_result", "attachment"]
    text: str | None = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    filename: str | None = None
    mime: str | None = None


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


class ConversationCreate(BaseModel):
    """Body for POST /conversations.

    ``agent_key`` selects the Coffer-managed agent to talk to (required — chat
    has no built-in agent of its own, ADR builtin-agent-is-internal-capability).
    ``agent_config`` is an opaque, agent-specific configuration object the named
    agent validates and stores (e.g. ``cwd`` for ``claude_code`` / ``codex``).
    """

    agent_key: str
    agent_config: dict[str, Any] | None = None


class ConversationPatch(BaseModel):
    """Body for PATCH /conversations/{id}."""

    title: str | None = None
    model_id: str | None = None


class AgentConfigPatch(BaseModel):
    """Body for PATCH /conversations/{id}/agent-config.

    Sets the managed agent's own model (free-text, passed through to its CLI).
    An empty or null ``model`` clears the override so the conversation inherits
    the active provider profile's projected default. ``cwd`` / ``session_id`` are
    preserved (ADR builtin-agent-is-internal-capability → ADR provider-switching).
    """

    model: str | None = None


class AgentConfigOut(BaseModel):
    """Read view of a conversation's agent config (managed agents).

    ``session_id`` is provider-internal and deliberately not surfaced.
    """

    cwd: str | None
    model: str | None


class ChannelBindingOut(BaseModel):
    """The IM channel a conversation is also driven from (ADR chat-single-owner-live-mirror).

    The return address for relaying the agent's output back to the channel;
    present iff the conversation has a channel binding.
    """

    channel: str
    chat_id: str


class ConversationOut(BaseModel):
    """Single conversation response."""

    id: str
    agent_key: str
    title: str
    model_id: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    # Optional channel binding, null for a desktop-only conversation
    # (ADR chat-single-owner-live-mirror).
    channel_binding: ChannelBindingOut | None = None


class ConversationListOut(BaseModel):
    """List of conversations, newest first."""

    conversations: list[ConversationOut]


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class MessageOut(BaseModel):
    """Single message response."""

    id: str
    conversation_id: str
    seq: int
    role: Literal["user", "assistant"]
    content: list[ContentBlockOut]
    status: Literal["complete", "streaming", "failed"]
    model_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    created_at: datetime


class MessageListOut(BaseModel):
    """List of messages for a conversation."""

    messages: list[MessageOut]


class SendMessageRequest(BaseModel):
    """Body for POST /conversations/{id}/messages."""

    text: str = Field(min_length=1, max_length=32768)


class SendMessageAck(BaseModel):
    """Response for POST /conversations/{id}/messages — fire-and-return
    (ADR chat-single-owner-live-mirror).

    ``queued`` is True when the message was enqueued behind an in-flight turn,
    False when its turn started immediately.
    """

    queued: bool


class PendingQueueIn(BaseModel):
    """Body for PUT /conversations/{id}/pending — replaces the ordered queue."""

    pending: list[str]


class PendingQueueOut(BaseModel):
    """The conversation's current ordered pending-message texts.

    ADR chat-single-owner-live-mirror.
    """

    pending: list[str]
