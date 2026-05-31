"""Pydantic request/response models for the chat HTTP surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from coffer.domain.chat.conversation import Conversation, Message


class CreateConversationIn(BaseModel):
    # ``<kind>:<name>`` of the target agent — ``builtin_agent:coffer`` or
    # ``agent:claude-code``.
    target_ref: str = Field(min_length=3, max_length=130)


class RenameConversationIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class SendMessageIn(BaseModel):
    text: str = Field(min_length=1)


class ConfirmIn(BaseModel):
    request_id: str = Field(min_length=1)
    approve: bool


class ToolCallOut(BaseModel):
    id: str
    tool: str
    args_summary: str
    result_summary: str | None = None
    confirmed: bool | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    status: str
    tool_calls: list[ToolCallOut]
    error: dict[str, Any] | None
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    target_ref: str
    title: str | None
    status: str
    model_snapshot: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ConversationListOut(BaseModel):
    items: list[ConversationOut]


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


def conversation_out(c: Conversation) -> ConversationOut:
    return ConversationOut(
        id=c.id,
        target_ref=c.target_ref,
        title=c.title,
        status=c.status.value,
        model_snapshot=c.model_snapshot,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        role=m.role.value,
        content=m.content,
        status=m.status.value,
        tool_calls=[
            ToolCallOut(
                id=t.id,
                tool=t.tool,
                args_summary=t.args_summary,
                result_summary=t.result_summary,
                confirmed=t.confirmed,
            )
            for t in m.tool_calls
        ],
        error=m.error,
        created_at=m.created_at,
    )
