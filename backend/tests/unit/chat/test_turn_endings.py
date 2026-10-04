"""Every way a turn can end: the platform's backstop, an interrupt, a delete and a
daemon shutdown (spec chat "Deliver partial output as events when a turn is interrupted or
fails": Coffer keeps no reply, the agent's session does).

* An adapter stream that simply stops, with no terminal event, is a
  ``stream_ended`` turn error detected by the platform — not a completed turn.
* A daemon shutdown cancelling the turn reports ``daemon_stopped``.
* A user interrupt ends it ``interrupted``; a delete ends it silently.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.application.chat.turn_orchestrator import active_turns
from coffer.application.chat.turn_runner import DAEMON_STOPPED
from coffer.application.chat.turn_state import stop_all_turns
from coffer.domain.chat.events import (
    STREAM_ENDED,
    STREAM_ENDED_MESSAGE,
    AgentEvent,
    TextDelta,
    TurnDone,
    TurnError,
    TurnStarted,
)
from tests.support.chat_turns import start_turn

from .conftest import FakeAgentAdapter
from .test_turn_orchestrator_with_fake_adapter import drain_queue, make_orchestrator

pytestmark = pytest.mark.asyncio


class _StreamThenBlock:
    """Streams ``deltas`` then blocks until cancelled; ``streamed`` fires after."""

    model_id = None

    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas
        self.streamed = asyncio.Event()

    async def run_turn(self, prompt: str, attachments: Any = ()) -> AsyncIterator[AgentEvent]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[AgentEvent]:
        yield TurnStarted()
        for text in self._deltas:
            yield TextDelta(text=text)
        self.streamed.set()
        await asyncio.Event().wait()


# ---------------------------------------------------------------------------
# Platform backstop: a stream that ends without a terminal event
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="chat",
    scenario="a stream that ends without a terminal is a failure, not a reply",
)
async def test_a_stream_that_stops_without_a_terminal_is_a_stream_ended_error() -> None:
    adapter = FakeAgentAdapter([TurnStarted(), TextDelta(text="cut mid-sen")])
    orchestrator, _conv, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    events = await drain_queue(await start_turn(orchestrator, conv.id, "hi"))

    assert events[-1] == TurnError(code=STREAM_ENDED, message=STREAM_ENDED_MESSAGE)
    assert not any(isinstance(e, TurnDone) for e in events)
    assert conv.id not in active_turns()


async def test_an_adapter_error_is_not_doubled_by_the_backstop() -> None:
    err = TurnError(code="provider_error", message="boom")
    adapter = FakeAgentAdapter([TurnStarted(), TextDelta(text="x"), err])
    orchestrator, _conv, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    events = await drain_queue(await start_turn(orchestrator, conv.id, "hi"))

    assert [e for e in events if isinstance(e, TurnError)] == [err]


# ---------------------------------------------------------------------------
# Cancellations
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="chat", scenario="a shutdown stops running turns first")
async def test_a_shutdown_cancellation_reports_the_daemon_stopped() -> None:
    adapter = _StreamThenBlock(["half an ", "answer"])
    orchestrator, _conv, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    await asyncio.wait_for(adapter.streamed.wait(), timeout=5.0)
    task = active_turns()[conv.id].task
    assert task is not None
    # Neither an interrupt nor a delete: the loop tearing the daemon down.
    task.cancel()
    events = await drain_queue(queue)
    with pytest.raises(asyncio.CancelledError):
        await task

    assert isinstance(events[-1], TurnError)
    assert events[-1].code == DAEMON_STOPPED
    # What had streamed was delivered ahead of the error.
    streamed = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert streamed == "half an answer"
    assert conv.id not in active_turns()


async def test_a_delete_ends_the_turn_without_a_terminal() -> None:
    adapter = _StreamThenBlock(["gone"])
    orchestrator, _conv, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    await asyncio.wait_for(adapter.streamed.wait(), timeout=5.0)
    orchestrator.cancel_turn(conv.id)
    events = await drain_queue(queue)

    assert not [e for e in events if isinstance(e, (TurnDone, TurnError))]


async def test_a_user_interrupt_ends_the_turn_as_interrupted() -> None:
    adapter = _StreamThenBlock(["kept"])
    orchestrator, _conv, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    await asyncio.wait_for(adapter.streamed.wait(), timeout=5.0)
    orchestrator.interrupt_turn(conv.id)
    events = await drain_queue(queue)

    assert events[-1] == TurnDone(
        prompt_tokens=None, completion_tokens=None, stop_reason="interrupted"
    )


async def test_stopping_every_turn_at_shutdown_awaits_them() -> None:
    """The daemon's teardown cancels running turns itself, before the database is
    disposed, and waits for each to finish — rather than leaving them to the
    event loop's own teardown, which runs after the engine is gone."""
    first, second = _StreamThenBlock(["one ", "half"]), _StreamThenBlock(["other"])
    orch_a, _c, _p = make_orchestrator(adapter=first)
    orch_b, _c2, _p2 = make_orchestrator(adapter=second)
    conv_a = await orch_a._chat.create_conversation(agent_key="builtin")
    conv_b = await orch_b._chat.create_conversation(agent_key="builtin")
    queue_a = await start_turn(orch_a, conv_a.id, "hi")
    queue_b = await start_turn(orch_b, conv_b.id, "hi")
    await asyncio.wait_for(first.streamed.wait(), timeout=5.0)
    await asyncio.wait_for(second.streamed.wait(), timeout=5.0)

    stopped = await stop_all_turns(timeout=5.0)

    assert stopped == 2
    assert active_turns() == {}
    for queue in (queue_a, queue_b):
        events = await drain_queue(queue)
        assert isinstance(events[-1], TurnError) and events[-1].code == DAEMON_STOPPED


async def test_stopping_turns_with_none_running_is_a_no_op() -> None:
    assert await stop_all_turns(timeout=1.0) == 0
