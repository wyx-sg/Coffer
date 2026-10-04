"""Daemon shutdown never starts a turn and never double-ends one (spec chat
"Queue messages sent during a turn").

* ``stop_all_turns`` holds every pending queue: a message queued behind a turn
  the shutdown cancels stays queued (and, the queue being in-memory, goes with
  the daemon) instead of starting a fresh turn during teardown.
* A shutdown cancel that lands while a finished turn is ending does not add a
  second terminal event.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.chat.turn_orchestrator import active_turns
from coffer.application.chat.turn_state import peek, stop_all_turns
from coffer.domain.chat.events import TextDelta, TurnDone, TurnError, TurnStarted
from tests.support.chat_turns import start_turn

from .conftest import FakeAgentAdapter, FakeAgentProvider
from .test_turn_endings import _StreamThenBlock
from .test_turn_orchestrator_with_fake_adapter import drain_queue, make_orchestrator

pytestmark = pytest.mark.asyncio


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


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# 1. Shutdown does not start queued turns
# ---------------------------------------------------------------------------


async def test_shutdown_does_not_start_the_queued_message() -> None:
    adapter = _StreamThenBlock(["half"])
    provider = _CountingProvider(adapter)
    orchestrator, _c, _p = make_orchestrator(provider=provider)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    assert await orchestrator.enqueue_message(conv.id, "first") is False
    await asyncio.wait_for(adapter.streamed.wait(), timeout=5.0)
    assert await orchestrator.enqueue_message(conv.id, "second") is True

    assert await stop_all_turns(timeout=5.0) == 1
    await _settle()

    assert active_turns() == {}
    assert provider.builds == 1
    # Held, not dropped: the in-memory queue goes with the daemon's process.
    assert orchestrator.pending(conv.id) == ["second"]


async def test_a_message_sent_while_stopping_is_queued_not_started() -> None:
    provider = _CountingProvider(FakeAgentAdapter([TurnStarted()]))
    orchestrator, _c, _p = make_orchestrator(provider=provider)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    await stop_all_turns(timeout=1.0)

    assert await orchestrator.enqueue_message(conv.id, "late") is True
    await _settle()

    assert provider.builds == 0
    assert orchestrator.pending(conv.id) == ["late"]


async def test_a_start_already_underway_is_awaited_and_does_not_run() -> None:
    """A start that was building its adapter when shutdown began: the shutdown
    waits for it, and it is turned back into a queued message."""
    provider = _CountingProvider(FakeAgentAdapter([TurnStarted()]))
    provider.gate = asyncio.Event()
    orchestrator, _c, _p = make_orchestrator(provider=provider)
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
    state = peek(conv.id)
    assert state is not None and state.paused
    assert orchestrator.pending(conv.id) == ["racing"]


# ---------------------------------------------------------------------------
# 2. A shutdown cancel during the end of a normal turn
# ---------------------------------------------------------------------------


async def test_a_shutdown_cancel_while_the_turn_ends_does_not_end_it_twice() -> None:
    done = TurnDone(prompt_tokens=3, completion_tokens=4, stop_reason="end_turn")
    adapter = FakeAgentAdapter([TurnStarted(), TextDelta(text="whole answer"), done])
    orchestrator, conv_repo, _p = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    entered, release = asyncio.Event(), asyncio.Event()
    real_touch = conv_repo.touch
    touches = 0

    async def slow_touch(conversation_id: str, updated_at: Any) -> None:
        nonlocal touches
        touches += 1
        if touches == 2:  # the end-of-turn bump (the first is the start)
            entered.set()
            await release.wait()
        await real_touch(conversation_id, updated_at)

    conv_repo.touch = slow_touch  # type: ignore[method-assign]
    queue = await start_turn(orchestrator, conv.id, "hi")
    await asyncio.wait_for(entered.wait(), timeout=5.0)
    task = active_turns()[conv.id].task
    assert task is not None

    task.cancel()  # the daemon going down, mid-finish
    await _settle()
    release.set()
    events = await drain_queue(queue)
    with pytest.raises(asyncio.CancelledError):
        await task

    terminals = [e for e in events if isinstance(e, (TurnDone, TurnError))]
    assert terminals == [done]
