"""Conversation + Message domain value objects (spec 008-builtin-agent-chat).

A conversation targets exactly one agent resource — either a ``builtin_agent``
(Coffer's own LLM loop) or an external ``agent`` (claude_code / codex). The
target is stored as a ``<kind>:<name>`` ref string and parsed back to a
``ResourceRef`` on demand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from coffer.domain.resource import ResourceRef


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class MessageStatus(StrEnum):
    STREAMING = "streaming"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class ToolCall:
    """A tool the agent invoked during a turn, embedded in its message.

    Argument/result are stored as short summaries only — never full payloads —
    mirroring the gateway invocation-logging discipline (no secret leakage).
    """

    id: str
    tool: str
    args_summary: str
    result_summary: str | None = None
    # None = confirmation not applicable; True/False = approved/denied.
    confirmed: bool | None = None


@dataclass
class Message:
    id: str
    conversation_id: str
    role: MessageRole
    content: str
    status: MessageStatus
    created_at: datetime
    tool_calls: list[ToolCall] = field(default_factory=list)
    error: dict[str, Any] | None = None


@dataclass
class Conversation:
    id: str
    target_ref: str
    title: str | None
    status: ConversationStatus
    model_snapshot: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @property
    def target(self) -> ResourceRef:
        return ResourceRef.parse(self.target_ref)

    @property
    def is_active(self) -> bool:
        return self.status is ConversationStatus.ACTIVE
