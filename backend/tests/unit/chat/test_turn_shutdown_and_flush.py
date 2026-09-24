"""Daemon shutdown never starts a turn, never double-ends one, and the partial
flush has a trailing write (spec chat "Keep partial output when a turn is
interrupted or fails", "Queue messages sent during a turn").

* ``stop_all_turns`` holds every pending queue: a message queued behind a turn
  the shutdown cancels stays queued (and, the queue being in-memory, goes with
  the daemon) instead of starting a fresh turn during teardown.
* A shutdown cancel that lands while a finished turn is being finalised does
  not add a second terminal event nor re-finalise the complete row as failed.
* Text streamed just before a long quiet stretch is persisted within about one
  flush interval, not only when the next event arrives.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.application.chat import turn_persistence
from coffer.application.chat.turn_orchestrator import active_turns, clear_active_turns
from coffer.application.chat.turn_state import peek, stop_all_turns
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnError, TurnStarted
from coffer.domain.chat.message import Message, Role, TextBlock

from .conftest import FakeAgentAdapter, FakeAgentProvider, FakeMessageRepo
from .test_turn_orchestrator_with_fake_adapter import drain_queue, make_orchestrator
from .test_turn_partial_output import _StreamThenBlock

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean() -> Any:
    clear_active_turns()
    yield
    clear_active_turns()


class _CountingProvider(FakeAgentProvider):
    """Counts adapter builds; ``gate`` (when set) holds each build until released."""

    def __init__(self, adapter: Any) -> None:
        super().__init__(adapter)
        self.builds = 0
        self.gate: asyncio.Event | None = None
        self.building = asyncio.Event()

    async def build_adapter(self, conversation_id: str) -> Any:
        self.builds += 1
        self.building.set()
        if self.gate is not None:
            await self.gate.wait()
        return await super().build_adapter(conversation_id)


def _rows(repo: FakeMessageRepo, role: Role) -> list[Message]:
    return [m for m in repo.all_messages() if m.role is role]


def _text(msg: Message) -> str:
    return "".join(b.text for b in msg.content if isinstance(b, TextBlock))


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# 1. Shutdown does not start queued turns
# ---------------------------------------------------------------------------


async def test_shutdown_does_not_start_the_queued_message() -> None:
    adapter = _StreamThenBlock(["half"])
    provider = _CountingProvider(adapter)
    orchestrator, _c, repo, _p = make_orchestrator(provider=provider)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    assert await orchestrator.enqueue_message(conv.id, "first") is False
    await asyncio.wait_for(adapter.streamed.wait(), timeout=5.0)
    assert await orchestrator.enqueue_message(conv.id, "second") is True

    assert await stop_all_turns(timeout=5.0) == 1
    await _settle()

    assert active_turns() == {}
    assert provider.builds == 1
    assert [_text(m) for m in _rows(repo, Role.USER)] == ["first"]
    assistants = _rows(repo, Role.ASSISTANT)
    assert [(a.status, _text(a)) for a in assistants] == [("failed", "half")]
    assert not [m for m in repo.all_messages() if m.status == "streaming"]
    # Held, not dropped: the in-memory queue goes with the daemon's process.
    assert orchestrator.pending(conv.id) == ["second"]


async def test_a_message_sent_while_stopping_is_queued_not_started() -> None:
    provider = _CountingProvider(FakeAgentAdapter([TurnStarted()]))
    orchestrator, _c, repo, _p = make_orchestrator(provider=provider)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    await stop_all_turns(timeout=1.0)

    assert await orchestrator.enqueue_message(conv.id, "late") is True
    await _settle()

    assert provider.builds == 0
    assert _rows(repo, Role.USER) == []
    assert orchestrator.pending(conv.id) == ["late"]


async def test_a_start_already_underway_is_awaited_and_does_not_run() -> None:
    """A start that was building its adapter when shutdown began: the shutdown
    waits for it, and it is turned back into a queued message."""
    provider = _CountingProvider(FakeAgentAdapter([TurnStarted()]))
    provider.gate = asyncio.Event()
    orchestrator, _c, repo, _p = make_orchestrator(provider=provider)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    send = asyncio.create_task(orchestrator.enqueue_message(conv.id, "racing"))
    await asyncio.wait_for(provider.building.wait(), timeout=5.0)

    stop = asyncio.create_task(stop_all_turns(timeout=5.0))
    await _settle()
    assert not stop.done()  # waits on the reserved-but-unstarted turn
    provider.gate.set()
    await asyncio.wait_for(stop, timeout=5.0)

    assert await send is True
    assert active_turns() == {}
    assert _rows(repo, Role.USER) == []
    assert _rows(repo, Role.ASSISTANT) == []
    state = peek(conv.id)
    assert state is not None and state.paused
    assert orchestrator.pending(conv.id) == ["racing"]


# ---------------------------------------------------------------------------
# 2. A shutdown cancel during the normal finalize
# ---------------------------------------------------------------------------


async def test_a_shutdown_cancel_during_finalize_does_not_end_the_turn_twice() -> None:
    done = TurnDone(prompt_tokens=3, completion_tokens=4, stop_reason="end_turn")
    adapter = FakeAgentAdapter([TurnStarted(), TextDelta(text="whole answer"), done])
    orchestrator, _c, repo, _p = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    entered, release = asyncio.Event(), asyncio.Event()
    real_finalize = repo.finalize

    async def slow_finalize(message_id: str, **kwargs: Any) -> None:
        entered.set()
        await release.wait()
        await real_finalize(message_id, **kwargs)

    repo.finalize = slow_finalize  # type: ignore[method-assign]
    queue = await orchestrator.start_turn(conv.id, "hi")
    await asyncio.wait_for(entered.wait(), timeout=5.0)
    task = active_turns()[conv.id].task
    assert task is not None

    task.cancel()  # the daemon going down, mid-finalize
    await _settle()
    release.set()
    events = await drain_queue(queue)
    with pytest.raises(asyncio.CancelledError):
        await task

    terminals = [e for e in events if isinstance(e, (TurnDone, TurnError))]
    assert terminals == [done]
    [assistant] = _rows(repo, Role.ASSISTANT)
    assert (assistant.status, _text(assistant)) == ("complete", "whole answer")
    assert (assistant.prompt_tokens, assistant.completion_tokens) == (3, 4)


# ---------------------------------------------------------------------------
# 3. Trailing partial flush
# ---------------------------------------------------------------------------


class _FakeTime:
    """A clock plus a sleep that advances it — sleeping is instant."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay
        await asyncio.sleep(0)

    async def sleep_until(self, delay: float) -> None:
        """Wait until the (event-driven) clock has moved ``delay`` on."""
        self.sleeps.append(delay)
        target = self.now + delay
        while self.now < target:
            await asyncio.sleep(0)


async def test_an_early_chunk_before_a_quiet_stretch_is_flushed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeTime()
    monkeypatch.setattr(turn_persistence, "_clock", fake.clock)
    monkeypatch.setattr(turn_persistence, "_sleep", fake.sleep)
    adapter = _StreamThenBlock(["early text"])  # then silence (a long tool run)
    orchestrator, _c, repo, _p = make_orchestrator(adapter=adapter)
    orchestrator._flush_interval = 1.0
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await orchestrator.start_turn(conv.id, "hi")
    await asyncio.wait_for(adapter.streamed.wait(), timeout=5.0)
    await _settle()

    [row] = _rows(repo, Role.ASSISTANT)
    assert (row.status, _text(row)) == ("streaming", "early text")
    assert repo.partial_writes == 1
    assert fake.sleeps and all(0 < s <= 1.0 for s in fake.sleeps)
    orchestrator.cancel_turn(conv.id)
    await drain_queue(queue)


async def test_trailing_flushes_keep_writes_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeTime()
    monkeypatch.setattr(turn_persistence, "_clock", fake.clock)
    monkeypatch.setattr(turn_persistence, "_sleep", fake.sleep_until)

    class _Ticking(FakeAgentAdapter):
        async def _yield_events(self) -> AsyncIterator[AgentEvent]:
            for event in self._events:
                fake.now += 0.1
                yield event
                await asyncio.sleep(0)  # let a scheduled trailing flush run

    tokens: list[AgentEvent] = [TextDelta(text=f"{i} ") for i in range(200)]
    done = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")
    orchestrator, _c, repo, _p = make_orchestrator(adapter=_Ticking([TurnStarted(), *tokens, done]))
    orchestrator._flush_interval = 1.0
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    await drain_queue(await orchestrator.start_turn(conv.id, "hi"))
    await _settle()

    # Trailing writes included, still at most one per interval: ~20 s of
    # streaming → ≤ 21 writes, not 200.
    assert 1 <= repo.partial_writes <= 21
    assert fake.sleeps  # the trailing path was exercised
    [assistant] = _rows(repo, Role.ASSISTANT)
    assert assistant.status == "complete"


async def test_no_partial_write_after_the_turn_is_finalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeTime()
    gate = asyncio.Event()

    async def held_sleep(delay: float) -> None:
        await gate.wait()
        fake.now += delay

    monkeypatch.setattr(turn_persistence, "_clock", fake.clock)
    monkeypatch.setattr(turn_persistence, "_sleep", held_sleep)
    done = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")
    adapter = FakeAgentAdapter([TurnStarted(), TextDelta(text="quick"), done])
    orchestrator, _c, repo, _p = make_orchestrator(adapter=adapter)
    orchestrator._flush_interval = 1.0
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    await drain_queue(await orchestrator.start_turn(conv.id, "hi"))
    gate.set()  # a trailing flush still pending would now fire
    await _settle()

    assert repo.partial_writes == 0
    [assistant] = _rows(repo, Role.ASSISTANT)
    assert (assistant.status, _text(assistant)) == ("complete", "quick")
