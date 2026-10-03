"""Pydantic schemas for the chat routes.

Every request/response body the web Conversations page's REST + SSE surface serves is
modelled here; the chat contract is generated from them (``make contracts``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from coffer.domain.channel_type import ChannelType
from coffer.domain.chat.attachment import MAX_ATTACHMENTS_PER_MESSAGE
from coffer.domain.chat.question import QuestionBlock, block_to_dict

# ---------------------------------------------------------------------------
# ContentBlock
# ---------------------------------------------------------------------------


class QuestionOptionOut(BaseModel):
    label: str
    description: str | None = None


class QuestionSpecOut(BaseModel):
    """One question of an ask."""

    header: str
    question: str
    multi_select: bool
    options: list[QuestionOptionOut]


class QuestionAnswerOut(BaseModel):
    """The answer to one question: the chosen option labels and/or typed text."""

    header: str
    selected: list[str]
    text: str | None = None


class QuestionOut(BaseModel):
    """A question the agent asked the owner (spec chat "Pause a turn on a
    question for the owner") — the ``question`` block of a reply, also the
    payload of the ``question_asked`` / ``question_closed`` events.

    ``answers`` holds the answers given so far, in order (a prefix of
    ``questions`` while ``status`` is ``pending``). ``answered_via`` is ``web`` or
    the answering channel's uid; ``answered_at`` is an ISO-8601 UTC instant."""

    question_id: str
    context: str | None = None
    questions: list[QuestionSpecOut]
    status: Literal["pending", "answered", "cancelled"]
    answers: list[QuestionAnswerOut]
    answered_via: str | None = None
    answered_by: str | None = None
    answered_at: str | None = None


def question_out(block: QuestionBlock) -> QuestionOut:
    """The wire model of a domain question block."""
    return QuestionOut.model_validate(block_to_dict(block))


class ContentBlockOut(BaseModel):
    """Wire representation of a ContentBlock (text | tool_use | tool_result |
    attachment | question). ``filename``/``mime`` describe an ``attachment`` reference; the
    local ``path`` is deliberately NOT surfaced (leak/security — spec chat
    "Re-materialise attachments from persisted history")."""

    type: Literal["text", "tool_use", "tool_result", "attachment", "question"]
    text: str | None = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    #: A ``tool_result``'s run time in milliseconds; null when unknown.
    duration_ms: int | None = None
    filename: str | None = None
    mime: str | None = None
    #: An ``attachment``'s id (what ``GET .../attachments/{id}`` takes) and byte
    #: size; null on channel media and on older blocks.
    attachment_id: str | None = None
    size: int | None = None
    #: The question of a ``question`` block.
    question: QuestionOut | None = None


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


class ConversationCreate(BaseModel):
    """Body for POST /conversations.

    ``agent_key`` selects the Coffer-managed agent to talk to (required — chat
    has no built-in agent of its own, ADR coffer-model-is-an-internal-engine).
    ``agent_config`` is an opaque, agent-specific configuration object the named
    agent validates and stores (e.g. ``cwd`` for ``claude_code`` / ``codex``).
    """

    agent_key: str
    agent_config: dict[str, Any] | None = None


class ConversationPatch(BaseModel):
    """Body for PATCH /conversations/{id}."""

    title: str | None = None


class AgentConfigPatch(BaseModel):
    """Body for PATCH /conversations/{id}/agent-config.

    Sets the managed agent's own model (free-text, passed through to its CLI)
    and how hard it should think. An empty or null ``model`` clears the override
    so the conversation inherits the active provider profile's projected
    default; an empty or null ``effort`` clears it so the agent keeps whatever
    its own config says. Each field is written only when the body mentions it,
    so setting one leaves the other alone; ``cwd`` / ``session_id`` are
    preserved (ADR coffer-model-is-an-internal-engine → ADR model-catalogue-read-from-the-agent).
    """

    model: str | None = None
    effort: str | None = None


class AgentConfigOut(BaseModel):
    """Read view of a conversation's agent config (managed agents).

    ``session_id`` is provider-internal and deliberately not surfaced.
    """

    cwd: str | None
    model: str | None
    #: The reasoning-effort level the turn runs at, for an agent that takes one.
    #: ``None`` means the agent's own default.
    effort: str | None = None


class UndeliveredReplyOut(BaseModel):
    """A message Coffer still owes the channel chat: a web ``reply`` or the
    agent's ``answer`` to it (spec chat "Mirror a web reply into the channel it
    came from")."""

    kind: Literal["reply", "answer"]
    text: str
    created_at: datetime


class ChannelMirrorOut(BaseModel):
    """Where a reply typed here will also be sent (spec chat "Show where a reply
    will also be sent").

    ``deliverable`` is False when a reply stays in Coffer; ``reason`` then says
    why: ``group_main`` (a group's main chat), ``not_located`` / ``chat_kind_unknown``
    (no chat to write to is known), ``channel_deleted``. ``target`` is the label
    shown before sending, e.g. ``SeaTalk · 🧵#1 deploy check``."""

    deliverable: bool
    #: The channel's type key; null when the channel has since been deleted.
    platform: ChannelType | None = None
    target: str
    reason: str | None = None
    undelivered: list[UndeliveredReplyOut] = Field(default_factory=list)


class ChannelPlaceOut(BaseModel):
    """Where in its channel a conversation lives — what the Conversations list's
    source badge names ("SeaTalk · DM · 🧵#2", "SeaTalk · <group> > thread")."""

    #: ``direct`` (a DM) or ``group``; null when the channel never said.
    chat_kind: Literal["direct", "group"] | None = None
    #: The conversation lives in a thread or topic, not the chat's main timeline.
    thread: bool = False
    #: The ``🧵#N title`` mark of a ``/thread`` parallel conversation.
    parallel_mark: str | None = None
    #: The group's display name, when Coffer knows one.
    chat_name: str | None = None


class ChannelBindingOut(BaseModel):
    """The IM channel a conversation is also driven from (ADR chat-single-owner-live-mirror).

    The return address for relaying the agent's output back to the channel;
    present iff the conversation has a channel binding.
    """

    #: The channel's identity — what a client follows to reach the channel.
    channel_uid: str
    #: The channel's label, resolved at read time. None when the channel has
    #: since been deleted: the conversation keeps its binding (it really did
    #: come from a channel), but there is no longer a name to show for it.
    channel: str | None
    chat_id: str
    #: The channel's type key (``seatalk`` / ``telegram``); null when the
    #: channel has since been deleted.
    platform: ChannelType | None = None
    #: Which chat and thread of the channel the conversation lives in; null
    #: when that is not known.
    place: ChannelPlaceOut | None = None
    #: Where a reply would also go. Filled on the single-conversation read
    #: only; null in the list, which stays cheap.
    mirror: ChannelMirrorOut | None = None


class ConversationOut(BaseModel):
    """Single conversation response."""

    id: str
    agent_key: str
    title: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    # Optional channel binding, null for a desktop-only conversation
    # (ADR chat-single-owner-live-mirror).
    channel_binding: ChannelBindingOut | None = None
    #: The newest message's words on one line (clipped), falling back to the
    #: newest message that has any; null when none does.
    preview: str | None = None
    #: A turn is in flight right now.
    running: bool = False
    #: A question the agent asked is waiting for the owner's answer (spec chat
    #: "Show which conversations wait on you").
    needs_you: bool = False


class ConversationListOut(BaseModel):
    """One page of conversations, newest activity first."""

    conversations: list[ConversationOut]
    #: Continues the listing after ``conversations``; null on the last page.
    next_cursor: str | None
    #: How many conversations match the listing (archived flag and ``q``),
    #: whatever the paging.
    total: int


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
    status: Literal["complete", "streaming", "stopped", "failed"]
    model_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    created_at: datetime
    #: When an assistant reply ended (complete, stopped or failed); null while it
    #: streams and on messages that never streamed.
    finished_at: datetime | None = None


class MessageListOut(BaseModel):
    """List of messages for a conversation."""

    messages: list[MessageOut]


class SendMessageRequest(BaseModel):
    """Body for POST /conversations/{id}/messages.

    ``attachment_ids`` name files uploaded through ``POST /attachments`` (spec
    chat "Send uploaded files with a web message"). A message carries text, at
    least one attachment, or both — never neither.
    """

    text: str = Field(default="", max_length=32768)
    attachment_ids: list[str] = Field(default_factory=list, max_length=MAX_ATTACHMENTS_PER_MESSAGE)

    @model_validator(mode="after")
    def _text_or_attachments(self) -> SendMessageRequest:
        if not self.text.strip() and not self.attachment_ids:
            raise ValueError("a message needs text or at least one attachment")
        return self


class ChatAttachmentOut(BaseModel):
    """Response for POST /attachments — one stored upload.

    ``id`` is what a send names; the file's local path never leaves the daemon
    (spec chat "Upload a file for a web message")."""

    id: str
    filename: str
    mime: str
    size: int


class SendMessageAck(BaseModel):
    """Response for POST /conversations/{id}/messages — fire-and-return
    (ADR chat-single-owner-live-mirror).

    ``queued`` is True when the message was enqueued behind an in-flight turn,
    False when its turn started immediately. ``mirror`` says what became of
    the reply in the channel the conversation came from (spec chat "Mirror a
    web reply into the channel it came from"): ``sent`` to the chat, ``pending``
    until the channel can send, ``kept`` in Coffer only; null for a conversation
    no channel drives.
    """

    queued: bool
    mirror: Literal["sent", "pending", "kept"] | None = None


class QuestionAnswerIn(BaseModel):
    """The owner's answer to one question: option labels and/or free text."""

    selected: list[str] = Field(default_factory=list, max_length=4)
    text: str | None = Field(default=None, max_length=4000)


class AnswerQuestionIn(BaseModel):
    """Body for POST .../questions/{question_id}/answer.

    ``answers`` answer the question's still-unanswered questions in order (one
    for the first, or several at once). ``index``, when given, names the question
    being answered: if that one was answered meanwhile the request is refused as
    ``QUESTION_CLOSED`` rather than answering the next."""

    answers: list[QuestionAnswerIn] = Field(min_length=1, max_length=4)
    index: int | None = Field(default=None, ge=0)


class NeedsYouCountOut(BaseModel):
    """How many conversations wait on an answer."""

    count: int


class PendingQueueIn(BaseModel):
    """Body for PUT /conversations/{id}/pending — replaces the ordered queue."""

    pending: list[str]


class PendingQueueOut(BaseModel):
    """The conversation's current ordered pending-message texts.

    ADR chat-single-owner-live-mirror.
    """

    pending: list[str]
