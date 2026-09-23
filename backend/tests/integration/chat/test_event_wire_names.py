"""The SSE event name is the event's own ``type``, verbatim (spec chat "Use the
wire event name as the type discriminator").

Driven through the real ``GET .../events`` route handler: the server-sent
events it yields are read straight off its body iterator, so what is checked
is exactly what a client receives.
"""

from __future__ import annotations

import asyncio
import json
import typing

import pytest

from coffer.application.chat.turn_orchestrator import clear_active_turns
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
}


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_active_turns()
    yield
    clear_active_turns()


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

    response = await subscribe_events(conv.id, svc=chat, orchestrator=orchestrator)
    stream = response.body_iterator
    await orchestrator.enqueue_message(conv.id, "hi")

    received: list[dict[str, str]] = []
    while True:
        item = await asyncio.wait_for(stream.__anext__(), 2.0)
        received.append(item)
        if item["event"] == "turn_done":
            break
    await stream.aclose()

    names = [item["event"] for item in received]
    assert "turn_start" in names and "tool_call" in names and "tool_result" in names
    for item in received:
        payload = json.loads(item["data"])
        assert item["event"] == payload["type"]
        assert item["event"] in _WIRE_NAMES


async def test_the_event_vocabulary_is_exactly_the_wire_names() -> None:
    members = typing.get_args(chat_events.AgentEvent)
    assert {cls.__dataclass_fields__["type"].default for cls in members} == _WIRE_NAMES
    # And each instance carries its class's name at runtime.
    assert QueueChanged(pending=[]).type == "queue_changed"
    assert TurnError(code="x", message="y").type == "turn_error"
