"""The wire shape of the chat turn-event stream (spec chat "Express a turn as
typed events").

``GET /api/v1/chat/conversations/{id}/events`` sends one SSE event per
:data:`coffer.domain.chat.events.AgentEvent`; the SSE ``event:`` name is the
model's ``type``, and the ``data:`` is the model itself. Modelling them here
puts the stream in the chat contract, so the frontend's types are generated
from it and a renamed field fails a gate instead of passing silently.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Literal

from pydantic import BaseModel, Field, RootModel

from coffer.domain.chat.events import AgentEvent


class TurnStartEventOut(BaseModel):
    """The data of a `turn_start` event: the agent loop began a turn."""

    type: Literal["turn_start"]


class TextDeltaEventOut(BaseModel):
    """The data of a `text_delta` event: a chunk of assistant text."""

    type: Literal["text_delta"]
    text: str


class ToolCallEventOut(BaseModel):
    """The data of a `tool_call` event: the agent requested a tool invocation."""

    type: Literal["tool_call"]
    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any]


class ToolResultEventOut(BaseModel):
    """The data of a `tool_result` event: the result or error of a prior `tool_call`."""

    type: Literal["tool_result"]
    tool_use_id: str
    tool_name: str
    output: dict[str, Any] | None
    error: str | None


class TurnDoneEventOut(BaseModel):
    """The data of a `turn_done` event: the turn completed (or was interrupted)."""

    type: Literal["turn_done"]
    prompt_tokens: int | None
    completion_tokens: int | None
    stop_reason: str = Field(
        description="Why the turn ended: `end_turn`, or `interrupted` when the user stopped it."
    )


class TurnErrorEventOut(BaseModel):
    """The data of a `turn_error` event: the turn failed."""

    type: Literal["turn_error"]
    code: str = Field(description="A short machine token, e.g. `stream_ended`, `turn_timeout`.")
    message: str


class QueueChangedEventOut(BaseModel):
    """The data of a `queue_changed` event: the pending-message queue changed."""

    type: Literal["queue_changed"]
    pending: list[str] = Field(description="The ordered texts still waiting to run as turns.")


class TurnEventMessage(
    RootModel[
        TurnStartEventOut
        | TextDeltaEventOut
        | ToolCallEventOut
        | ToolResultEventOut
        | TurnDoneEventOut
        | TurnErrorEventOut
        | QueueChangedEventOut
    ]
):
    """The `data:` of one event on `GET /api/v1/chat/conversations/{id}/events`,
    chosen by its SSE `event:` name (which equals the model's `type`)."""


def turn_event_message(event: AgentEvent) -> TurnEventMessage:
    """The wire model of one domain event."""
    return TurnEventMessage.model_validate(dataclasses.asdict(event))


__all__ = [
    "QueueChangedEventOut",
    "TextDeltaEventOut",
    "ToolCallEventOut",
    "ToolResultEventOut",
    "TurnDoneEventOut",
    "TurnErrorEventOut",
    "TurnEventMessage",
    "TurnStartEventOut",
    "turn_event_message",
]
