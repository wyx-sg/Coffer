"""Runtime event value objects + the turn request DTO.

These are the pure, engine-agnostic units a runtime streams while it works a
turn. The ``AgentRuntime`` *port* (a Protocol) lives in
``coffer.application.chat.ports`` so application code depends only on ports it
defines; these value objects stay in the domain so every layer can name them.

``event_payload`` maps an event to the JSON dict the HTTP surface streams over
SSE — kept here so the wire shape is defined once, next to the events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True)
class TurnMessage:
    """One prior message handed to the runtime as conversation history."""

    role: str  # "user" | "assistant" | "tool"
    content: str


@dataclass(frozen=True)
class ChatTurnRequest:
    """Everything a runtime needs to work one user turn."""

    history: list[TurnMessage]
    user_message: str
    confirm_tools: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TextDelta:
    KIND: ClassVar[str] = "text_delta"
    text: str


@dataclass(frozen=True)
class ToolCallStarted:
    KIND: ClassVar[str] = "tool_call"
    id: str
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolResultEvent:
    KIND: ClassVar[str] = "tool_result"
    id: str
    tool: str
    ok: bool
    summary: str


@dataclass(frozen=True)
class ConfirmationRequest:
    KIND: ClassVar[str] = "confirmation"
    id: str
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ErrorEvent:
    KIND: ClassVar[str] = "error"
    code: str
    message: str


@dataclass(frozen=True)
class DoneEvent:
    KIND: ClassVar[str] = "done"


RuntimeEvent = (
    TextDelta | ToolCallStarted | ToolResultEvent | ConfirmationRequest | ErrorEvent | DoneEvent
)


def event_payload(ev: RuntimeEvent) -> dict[str, Any]:
    """Map a runtime event to its SSE JSON payload (``type`` discriminator)."""
    if isinstance(ev, TextDelta):
        return {"type": ev.KIND, "text": ev.text}
    if isinstance(ev, ToolCallStarted):
        return {"type": ev.KIND, "id": ev.id, "tool": ev.tool, "args": ev.args}
    if isinstance(ev, ToolResultEvent):
        return {"type": ev.KIND, "id": ev.id, "tool": ev.tool, "ok": ev.ok, "summary": ev.summary}
    if isinstance(ev, ConfirmationRequest):
        return {"type": ev.KIND, "id": ev.id, "tool": ev.tool, "args": ev.args}
    if isinstance(ev, ErrorEvent):
        return {"type": ev.KIND, "code": ev.code, "message": ev.message}
    if isinstance(ev, DoneEvent):
        return {"type": ev.KIND}
    raise AssertionError(f"unhandled runtime event: {ev!r}")  # pragma: no cover
