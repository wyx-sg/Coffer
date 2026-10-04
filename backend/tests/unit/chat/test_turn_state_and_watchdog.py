"""The orchestrator's per-conversation state: one ``TurnState`` per
conversation, released once idle; the idle watchdog that bounds a wedged turn;
and the pending queue a channel message rides with its renderer hook.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.application.chat.turn_orchestrator import (
    active_turns,
    held_conversations,
)
from coffer.application.chat.turn_state import peek
from coffer.domain.chat.events import (
    TURN_TIMEOUT,
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

_DONE = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


async def _settle() -> None:
    """Let the turn task finish and the auto-advance callback run."""
    for _ in range(10):
        await asyncio.sleep(0)


class _StallingAdapter:
    """Streams one delta, then never produces another event — a wedged agent.

    Records whether its cancellation path ran: that is where a real adapter
    interrupts and terminates its subprocess, so it is what the watchdog owes.
    """

    model_id = None

    def __init__(self) -> None:
        self.cancelled = False
        self.stalled = asyncio.Event()

    async def run_turn(self, prompt: str, attachments: Any = ()) -> AsyncIterator[AgentEvent]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[AgentEvent]:
        yield TurnStarted()
        yield TextDelta(text="half an answer")
        self.stalled.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


# ---------------------------------------------------------------------------
# Idle watchdog
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="chat", scenario="a silent turn is cancelled by the idle watchdog")
async def test_a_turn_with_no_event_for_the_idle_window_is_cancelled_as_a_timeout() -> None:
    adapter = _StallingAdapter()
    orchestrator, _conv, _prov = make_orchestrator(adapter=adapter)
    orchestrator._idle_timeout = 0.05
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    events = await drain_queue(queue)

    terminals = [e for e in events if isinstance(e, (TurnDone, TurnError))]
    assert len(terminals) == 1
    assert isinstance(terminals[0], TurnError)
    assert terminals[0].code == TURN_TIMEOUT
    assert "0.05s" in terminals[0].message
    # The adapter's own cancellation path ran — the subprocess teardown lives there.
    assert adapter.cancelled is True
    # The slot is free.
    assert conv.id not in active_turns()


async def test_events_inside_the_window_keep_a_turn_alive() -> None:
    class _Slow(FakeAgentAdapter):
        async def _yield_events(self) -> AsyncIterator[AgentEvent]:
            for event in self._events:
                await asyncio.sleep(0.02)  # each gap is inside the 0.1 s window
                yield event

    adapter = _Slow([TurnStarted(), TextDelta(text="a"), TextDelta(text="b"), _DONE])
    orchestrator, _conv, _prov = make_orchestrator(adapter=adapter)
    orchestrator._idle_timeout = 0.1
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    events = await drain_queue(await start_turn(orchestrator, conv.id, "hi"))

    assert events[-1] == _DONE
    assert not any(isinstance(e, TurnError) for e in events)


async def test_a_disabled_watchdog_waits_indefinitely() -> None:
    adapter = _StallingAdapter()
    orchestrator, _conv, _prov = make_orchestrator(adapter=adapter)
    orchestrator._idle_timeout = None
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    await asyncio.wait_for(adapter.stalled.wait(), timeout=1.0)
    await asyncio.sleep(0.1)  # far longer than the windows the tests above use

    assert conv.id in active_turns()
    assert adapter.cancelled is False
    orchestrator.cancel_turn(conv.id)  # cleanup
    await drain_queue(queue)


async def test_an_interrupt_during_the_window_is_still_an_interrupt() -> None:
    adapter = _StallingAdapter()
    orchestrator, _conv, _prov = make_orchestrator(adapter=adapter)
    orchestrator._idle_timeout = 10.0
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    await asyncio.wait_for(adapter.stalled.wait(), timeout=1.0)
    orchestrator.interrupt_turn(conv.id)
    events = await drain_queue(queue)

    assert events[-1] == TurnDone(
        prompt_tokens=None, completion_tokens=None, stop_reason="interrupted"
    )
    assert not any(isinstance(e, TurnError) for e in events)


# ---------------------------------------------------------------------------
# State lifetime
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="chat", scenario="turn state is released when nothing needs it")
async def test_finishing_a_turn_releases_the_conversation_state() -> None:
    orchestrator, _conv, _prov = make_orchestrator([TextDelta(text="x"), _DONE])
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    await orchestrator.enqueue_message(conv.id, "hi")
    assert conv.id in held_conversations()
    await _settle()

    assert conv.id not in active_turns()
    assert conv.id not in held_conversations()
    assert orchestrator.pending(conv.id) == []


async def test_a_pending_message_keeps_the_state_while_paused() -> None:
    orchestrator, _conv, _prov = make_orchestrator([TextDelta(text="x"), _DONE])
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    await orchestrator.enqueue_message(conv.id, "one")
    await orchestrator.enqueue_message(conv.id, "two")
    orchestrator.interrupt_turn(conv.id)
    await _settle()

    assert orchestrator.pending(conv.id) == ["two"]
    assert conv.id in held_conversations()
    state = peek(conv.id)
    assert state is not None and state.paused is True


async def test_cancel_turn_drops_the_state() -> None:
    orchestrator, _conv, _prov = make_orchestrator([TextDelta(text="x"), _DONE])
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    await orchestrator.enqueue_message(conv.id, "one")
    await orchestrator.enqueue_message(conv.id, "two")
    assert conv.id in held_conversations()

    orchestrator.cancel_turn(conv.id)

    assert conv.id not in held_conversations()
    assert orchestrator.pending(conv.id) == []


# ---------------------------------------------------------------------------
# A channel message on the shared queue
# ---------------------------------------------------------------------------


async def test_a_channel_message_queues_behind_a_running_turn_and_gets_its_own_stream() -> None:
    release = asyncio.Event()

    class _Gated(FakeAgentAdapter):
        async def _yield_events(self) -> AsyncIterator[AgentEvent]:
            yield TurnStarted()
            await release.wait()
            yield TextDelta(text="reply")
            yield _DONE

    orchestrator, _conv, _prov = make_orchestrator(adapter=_Gated([]))
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    handed: list[asyncio.Queue[Any]] = []

    await orchestrator.enqueue_message(conv.id, "from the first")
    queued = await orchestrator.enqueue_message(
        conv.id, "from the phone", title_hint="phone", on_start=handed.append
    )

    assert queued is True
    assert handed == []  # not started yet — the renderer is not attached
    assert orchestrator.pending(conv.id) == ["from the phone"]

    release.set()
    await _settle()
    assert len(handed) == 1  # its turn began; the channel got its stream
    events = await drain_queue(handed[0])
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["reply"]
    assert isinstance(events[-1], TurnDone)
    assert orchestrator.pending(conv.id) == []


@pytest.mark.acceptance(
    spec="chat",
    scenario="a queued turn that fails to start is held, not lost",
)
async def test_a_channel_message_that_cannot_start_hears_the_failure() -> None:
    from coffer.domain.chat.errors import AgentConfigRejected

    from .conftest import FakeAgentProvider

    release = asyncio.Event()

    class _Gated(FakeAgentAdapter):
        async def _yield_events(self) -> AsyncIterator[AgentEvent]:
            yield TurnStarted()
            await release.wait()
            yield _DONE

    provider = FakeAgentProvider(_Gated([]))
    orchestrator, _conv, _prov = make_orchestrator(provider=provider)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    handed: list[asyncio.Queue[Any]] = []

    await orchestrator.enqueue_message(conv.id, "running")
    await orchestrator.enqueue_message(conv.id, "phone", on_start=handed.append)
    provider._build_error = AgentConfigRejected("missing_secret", "no secret")
    release.set()
    await _settle()

    # The head is kept (paused) and the channel is told, not left in silence.
    assert orchestrator.pending(conv.id) == ["phone"]
    assert len(handed) == 1
    events = await drain_queue(handed[0])
    assert events == [TurnError(code="INTERNAL_ERROR", message="failed to start queued turn")]
