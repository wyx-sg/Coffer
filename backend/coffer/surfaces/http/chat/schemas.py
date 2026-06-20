"""Pydantic schemas matching specs/008-agent-chat/contracts/api.openapi.yaml.

Every request/response body in the Chat + Models API is modelled here.
Field names, types, and nullability mirror the yaml exactly.
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
    """Wire representation of a ContentBlock (text | tool_use | tool_result)."""

    type: Literal["text", "tool_use", "tool_result"]
    text: str | None = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


class ConversationCreate(BaseModel):
    """Body for POST /conversations.

    ``agent_key`` selects the Coffer-managed agent to talk to (required — chat
    has no built-in agent since ADR-024). ``agent_config`` is an opaque,
    agent-specific configuration object the named agent validates and stores
    (e.g. ``cwd`` for ``claude_code`` / ``codex``).
    """

    agent_key: str
    agent_config: dict[str, Any] | None = None


class ConversationPatch(BaseModel):
    """Body for PATCH /conversations/{id}."""

    title: str | None = None
    model_id: str | None = None


class ChannelBindingOut(BaseModel):
    """The IM channel a conversation is also driven from (ADR-031).

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
    # ADR-031 — optional channel binding (null for a desktop-only conversation).
    channel_binding: ChannelBindingOut | None = None


class ConversationListOut(BaseModel):
    """List of conversations, newest first."""

    conversations: list[ConversationOut]


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


class ChatAgentOut(BaseModel):
    """One agent the chat platform offers.

    Named ``ChatAgent*`` (not ``Agent*``) to stay distinct from the spec-003
    agent-registry schemas in the generated OpenAPI components.
    """

    agent_key: str
    display_name: str
    available: bool


class ChatAgentListOut(BaseModel):
    """The agents the chat platform offers."""

    agents: list[ChatAgentOut]


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
    """Response for POST /conversations/{id}/messages (fire-and-return, ADR-031).

    ``queued`` is True when the message was enqueued behind an in-flight turn,
    False when its turn started immediately.
    """

    queued: bool


class PendingQueueIn(BaseModel):
    """Body for PUT /conversations/{id}/pending — replaces the ordered queue."""

    pending: list[str]


class PendingQueueOut(BaseModel):
    """The conversation's current ordered pending-message texts (ADR-031)."""

    pending: list[str]


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class ModelCreate(BaseModel):
    """Body for POST /models."""

    display_name: str = Field(min_length=1)
    provider: Literal["anthropic", "openai", "ollama"]
    model: str = Field(min_length=1)
    credential_ref: str | None = None
    base_url: str | None = None
    is_default: bool = False


class ModelPatch(BaseModel):
    """Body for PATCH /models/{id}."""

    display_name: str | None = None
    model: str | None = None
    credential_ref: str | None = None
    base_url: str | None = None
    is_default: bool | None = None


class ModelOut(BaseModel):
    """Single model config response."""

    id: str
    display_name: str
    provider: Literal["anthropic", "openai", "ollama"]
    model: str
    credential_ref: str | None = None
    base_url: str | None = None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ModelListOut(BaseModel):
    """List of configured models."""

    models: list[ModelOut]


# --- provider introspection (test connection + list models) ----------------


class TestConnectionIn(BaseModel):
    provider: str
    model: str
    credential_ref: str | None = None
    base_url: str | None = None


class ListModelsIn(BaseModel):
    provider: str
    credential_ref: str | None = None
    base_url: str | None = None


class TestResultOut(BaseModel):
    ok: bool
    message: str
    detail: dict[str, object] = {}


class ProviderModelsOut(BaseModel):
    models: list[str]
    message: str = ""


class EmbeddingTestIn(BaseModel):
    provider: str
    model: str
    credential_ref: str | None = None
    base_url: str | None = None
