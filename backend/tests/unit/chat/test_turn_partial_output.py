"""Partial output survives every way a turn can end short (spec chat "Keep partial
output when a turn is interrupted or fails").

* An adapter stream that simply stops, with no terminal event, is a
  ``stream_ended`` turn error detected by the platform — not a completed turn.
* The accumulated reply is flushed onto the ``streaming`` row while it streams
  (throttled), so a daemon that dies mid-turn leaves the text for the startup
  sweep to mark failed.
* A daemon shutdown cancelling the turn keeps the partial, marked failed.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.application.chat import turn_persistence
from coffer.application.chat.turn_orchestrator import active_turns, clear_active_turns
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
from coffer.domain.chat.message import Message, Role, TextBlock

from .conftest import FakeAgentAdapter, FakeMessageRepo
from .test_turn_orchestrator_with_fake_adapter import drain_queue, make_orchestrator

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean() -> Any:
    clear_active_turns()
    yield
    clear_active_turns()


def _assistant(msg_repo: FakeMessageRepo) -> Message:
    rows = [m for m in msg_repo.all_messages() if m.role is Role.ASSISTANT]
    assert len(rows) == 1
    return rows[0]


def _text(msg: Message) -> str:
    return "".join(b.text for b in msg.content if isinstance(b, TextBlock))


class _StreamThenBlock:
    """Streams ``deltas`` then blocks until cancelled; ``streamed`` fires after.

    ``before_delta`` runs ahead of each delta (tests advance a fake clock there —
    the turn task drains a ready generator without yielding to the test)."""

    model_id = None

    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas
        self.streamed = asyncio.Event()
        self.before_delta: list[Any] = []

    async def run_turn(self, *, history: Any, **_: object) -> AsyncIterator[AgentEvent]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[AgentEvent]:
        yield TurnStarted()
        for i, text in enumerate(self._deltas):
            if i < len(self.before_delta):
                self.before_delta[i]()
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
    orchestrator, _conv, msg_repo, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    subscriber = orchestrator.subscribe(conv.id)

    events = await drain_queue(await orchestrator.start_turn(conv.id, "hi"))

    backstop = TurnError(code=STREAM_ENDED, message=STREAM_ENDED_MESSAGE)
    assert events[-1] == backstop
    assert not any(isinstance(e, TurnDone) for e in events)
    # Subscribers hear it too — the bus carries the same terminal.
    seen: list[AgentEvent] = []
    while not subscriber.empty():
        item = subscriber.get_nowait()
        if item is not None:
            seen.append(item)
    assert backstop in seen
    assistant = _assistant(msg_repo)
    assert assistant.status == "failed"
    assert _text(assistant) == "cut mid-sen"
    assert conv.id not in active_turns()


async def test_an_adapter_error_is_not_doubled_by_the_backstop() -> None:
    err = TurnError(code="provider_error", message="boom")
    adapter = FakeAgentAdapter([TurnStarted(), TextDelta(text="x"), err])
    orchestrator, _conv, _msg, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    events = await drain_queue(await orchestrator.start_turn(conv.id, "hi"))

    assert [e for e in events if isinstance(e, TurnError)] == [err]


# ---------------------------------------------------------------------------
# Throttled partial flush
# ---------------------------------------------------------------------------


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.acceptance(
    spec="chat",
    scenario="a daemon that dies mid-turn keeps what was streamed",
)
async def test_partial_output_is_flushed_to_the_streaming_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(turn_persistence, "_clock", clock)
    adapter = _StreamThenBlock(["first ", "second"])
    orchestrator, _conv, msg_repo, _prov = make_orchestrator(adapter=adapter)
    orchestrator._flush_interval = 1.0
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    def _pass_interval() -> None:
        clock.now += 5.0

    adapter.before_delta = [_pass_interval]  # only before the first delta
    queue = await orchestrator.start_turn(conv.id, "hi")
    await asyncio.wait_for(adapter.streamed.wait(), timeout=5.0)
    await asyncio.sleep(0)

    row = _assistant(msg_repo)
    assert row.status == "streaming"
    assert _text(row) == "first "  # flushed on the first delta after the interval
    assert msg_repo.partial_writes == 1
    orchestrator.cancel_turn(conv.id)
    await drain_queue(queue)


@pytest.mark.acceptance(
    spec="chat",
    scenario="a daemon that dies mid-turn keeps what was streamed",
)
async def test_the_flush_does_not_write_on_every_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(turn_persistence, "_clock", clock)

    class _Ticking(FakeAgentAdapter):
        async def _yield_events(self) -> AsyncIterator[AgentEvent]:
            for event in self._events:
                clock.now += 0.1  # 200 tokens over 20 s of wall time
                yield event

    tokens: list[AgentEvent] = [TextDelta(text=f"{i} ") for i in range(200)]
    done = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")
    orchestrator, _conv, msg_repo, _prov = make_orchestrator(
        adapter=_Ticking([TurnStarted(), *tokens, done])
    )
    orchestrator._flush_interval = 1.0
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    await drain_queue(await orchestrator.start_turn(conv.id, "hi"))

    # At most one write per interval: ~20 s of streaming → ≤ 21 writes, not 200.
    assert 1 <= msg_repo.partial_writes <= 21
    assistant = _assistant(msg_repo)
    assert assistant.status == "complete"
    assert _text(assistant) == "".join(f"{i} " for i in range(200))


async def test_a_quick_turn_writes_no_partial_at_all() -> None:
    done = TurnDone(prompt_tokens=1, completion_tokens=2, stop_reason="end_turn")
    adapter = FakeAgentAdapter([TurnStarted(), TextDelta(text="hello"), done])
    orchestrator, _conv, msg_repo, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    await drain_queue(await orchestrator.start_turn(conv.id, "hi"))

    assert msg_repo.partial_writes == 0
    assistant = _assistant(msg_repo)
    assert (assistant.status, _text(assistant)) == ("complete", "hello")
    assert (assistant.prompt_tokens, assistant.completion_tokens) == (1, 2)


# ---------------------------------------------------------------------------
# Daemon shutdown cancellation
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="chat",
    scenario="a shutdown keeps the partial reply",
)
async def test_a_shutdown_cancellation_keeps_the_partial_marked_failed() -> None:
    adapter = _StreamThenBlock(["half an ", "answer"])
    orchestrator, _conv, msg_repo, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await orchestrator.start_turn(conv.id, "hi")
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
    assistant = _assistant(msg_repo)
    assert assistant.status == "failed"
    assert _text(assistant) == "half an answer"
    assert conv.id not in active_turns()


async def test_a_delete_still_discards_the_partial() -> None:
    adapter = _StreamThenBlock(["gone"])
    orchestrator, _conv, msg_repo, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await orchestrator.start_turn(conv.id, "hi")
    await asyncio.wait_for(adapter.streamed.wait(), timeout=5.0)
    orchestrator.cancel_turn(conv.id)
    await drain_queue(queue)

    assert not [m for m in msg_repo.all_messages() if m.role is Role.ASSISTANT]


async def test_a_user_interrupt_is_unchanged_complete_with_partial() -> None:
    adapter = _StreamThenBlock(["kept"])
    orchestrator, _conv, msg_repo, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await orchestrator.start_turn(conv.id, "hi")
    await asyncio.wait_for(adapter.streamed.wait(), timeout=5.0)
    orchestrator.interrupt_turn(conv.id)
    events = await drain_queue(queue)

    assert events[-1] == TurnDone(
        prompt_tokens=None, completion_tokens=None, stop_reason="interrupted"
    )
    assistant = _assistant(msg_repo)
    assert (assistant.status, _text(assistant)) == ("complete", "kept")


@pytest.mark.acceptance(
    spec="chat",
    scenario="a shutdown keeps the partial reply",
)
async def test_stopping_every_turn_at_shutdown_awaits_them_and_keeps_partials() -> None:
    """The daemon's teardown cancels running turns itself, before the database is
    disposed, and waits for each to finish writing its partial reply — rather than
    leaving them to the event loop's own teardown, which runs after the engine is
    gone."""
    first, second = _StreamThenBlock(["one ", "half"]), _StreamThenBlock(["other"])
    orch_a, _c, repo_a, _p = make_orchestrator(adapter=first)
    orch_b, _c2, repo_b, _p2 = make_orchestrator(adapter=second)
    conv_a = await orch_a._chat.create_conversation(agent_key="builtin")
    conv_b = await orch_b._chat.create_conversation(agent_key="builtin")
    await orch_a.start_turn(conv_a.id, "hi")
    await orch_b.start_turn(conv_b.id, "hi")
    await asyncio.wait_for(first.streamed.wait(), timeout=5.0)
    await asyncio.wait_for(second.streamed.wait(), timeout=5.0)

    stopped = await stop_all_turns(timeout=5.0)

    assert stopped == 2
    assert active_turns() == {}
    for repo, text in ((repo_a, "one half"), (repo_b, "other")):
        assistant = _assistant(repo)
        assert assistant.status == "failed"
        assert _text(assistant) == text


async def test_stopping_turns_with_none_running_is_a_no_op() -> None:
    assert await stop_all_turns(timeout=1.0) == 0
