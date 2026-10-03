"""The SSE event name is the event's own ``type``, verbatim (spec chat "Use the
wire event name as the type discriminator").

Driven through the real ``GET .../events`` route handler: the server-sent
events it yields are read straight off its body iterator, so what is checked
is exactly what a client receives.
"""

from __future__ import annotations

import asyncio
import typing

import pytest

from coffer.domain.chat import events as chat_events
from coffer.domain.chat.events import (
    QueueChanged,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
    TurnStarted,
)
from coffer.surfaces.http.chat.turn_routes import subscribe_events
from tests.unit.chat.conftest import make_chat_services

pytestmark = pytest.mark.asyncio

_WIRE_NAMES = {
    "turn_start",
    "text_delta",
    "tool_call",
    "tool_result",
    "turn_done",
    "turn_error",
    "queue_changed",
    "question_asked",
    "question_closed",
}


@pytest.mark.acceptance(spec="chat", scenario="each event is named on the wire by its own type")
async def test_each_sse_event_is_named_by_its_payload_type() -> None:
    scripted = [
        TurnStarted(),
        TextDelta(text="looking"),
        ToolCall(tool_use_id="t1", tool_name="read_file", tool_input={"path": "/a"}),
        ToolResult(tool_use_id="t1", tool_name="read_file", output={"text": "x"}, error=None),
        TurnDone(prompt_tokens=1, completion_tokens=2, stop_reason="end_turn"),
    ]
    chat, orchestrator, _registry = make_chat_services(scripted)
    conv = await chat.create_conversation(agent_key="builtin")

    stream = subscribe_events(conv.id, svc=chat, orchestrator=orchestrator)
    # The generator subscribes when first advanced, so start it before the turn.
    first = asyncio.ensure_future(stream.__anext__())
    await asyncio.sleep(0)
    await orchestrator.enqueue_message(conv.id, "hi")

    received: list[typing.Any] = []
    while True:
        item = await asyncio.wait_for(first, 2.0)
        received.append(item)
        if item.event == "turn_done":
            break
        first = asyncio.ensure_future(stream.__anext__())
    await stream.aclose()

    names = [item.event for item in received]
    assert "turn_start" in names and "tool_call" in names and "tool_result" in names
    for item in received:
        assert item.event == item.data.root.type
        assert item.event in _WIRE_NAMES


async def test_the_event_vocabulary_is_exactly_the_wire_names() -> None:
    members = typing.get_args(chat_events.AgentEvent)
    assert {cls.__dataclass_fields__["type"].default for cls in members} == _WIRE_NAMES
    # And each instance carries its class's name at runtime.
    assert QueueChanged(pending=[]).type == "queue_changed"
    assert TurnError(code="x", message="y").type == "turn_error"


@pytest.mark.acceptance(
    spec="chat", scenario="the event stream's wire shape is generated from the contract"
)
async def test_every_event_has_a_wire_model_with_exactly_its_fields() -> None:
    """A field renamed on a domain event breaks this, and the contract diff with it."""
    import dataclasses

    from coffer.surfaces.http.chat import event_schemas as wire

    models = {
        "turn_start": wire.TurnStartEventOut,
        "text_delta": wire.TextDeltaEventOut,
        "tool_call": wire.ToolCallEventOut,
        "tool_result": wire.ToolResultEventOut,
        "turn_done": wire.TurnDoneEventOut,
        "turn_error": wire.TurnErrorEventOut,
        "queue_changed": wire.QueueChangedEventOut,
        "question_asked": wire.QuestionAskedEventOut,
        "question_closed": wire.QuestionClosedEventOut,
    }
    members = typing.get_args(chat_events.AgentEvent)
    assert {cls.__dataclass_fields__["type"].default for cls in members} == set(models)
    for cls in members:
        name = cls.__dataclass_fields__["type"].default
        assert {f.name for f in dataclasses.fields(cls)} == set(models[name].model_fields), name
