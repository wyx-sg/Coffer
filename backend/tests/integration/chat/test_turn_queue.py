"""Pending-queue behaviour, tested at the orchestrator level where turn timing is
deterministic.

A turn runs as a detached task, so the deep behaviours (FIFO queueing,
interrupt-pauses-queue, a stop from another surface) are exercised here by
driving a controllable adapter and a renderer sink, rather than through the sync
TestClient (which cannot observe a detached task).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence

import pytest

from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import (
    TurnOrchestrator,
    active_turns,
)
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from tests.unit.chat.conftest import (
    FakeAgentAdapter,
    FakeConversationRepo,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SeqProvider:
    """Provider that hands out a pre-built adapter per ``build_adapter`` call."""

    agent_key = "builtin"

    def __init__(self, adapters: Sequence[object]) -> None:
        self._adapters = list(adapters)
        self.builds = 0

    async def init_conversation(self, conversation_id: str, agent_config: dict) -> None:
        return None

    async def build_adapter(self, conversation_id: str) -> object:
        # Clamp so exhausting the list reuses the last adapter instead of raising.
        idx = min(self.builds, len(self._adapters) - 1)
        self.builds += 1
        return self._adapters[idx]

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        return None

    async def availability(self) -> bool:
        return True


class _BlockingAdapter:
    """Yields turn_start + a text delta, then blocks until ``release`` is set
    before emitting turn_done — so the turn stays in flight under test control."""

    model_id: str | None = None

    def __init__(self, release: asyncio.Event, *, text: str = "working") -> None:
        self._release = release
        self._text = text

    async def run_turn(self, prompt: str, attachments: object = ()) -> AsyncIterator[AgentEvent]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[AgentEvent]:
        yield TurnStarted()
        yield TextDelta(text=self._text)
        await self._release.wait()
        yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


def _make_orch(provider: object) -> tuple[TurnOrchestrator, ChatService]:
    conv_repo = FakeConversationRepo()
    registry = AgentProviderRegistry()
    registry.register(provider, display_name="Coffer Assistant")  # type: ignore[arg-type]
    chat = ChatService(conversations=conv_repo, registry=registry)
    orch = TurnOrchestrator(chat_service=chat, registry=registry)
    return orch, chat


async def _collect_until(
    queue: asyncio.Queue,
    predicate: Callable[[object], bool],
    *,
    timeout: float = 2.0,
) -> list[object]:
    out: list[object] = []
    while True:
        ev = await asyncio.wait_for(queue.get(), timeout)
        if ev is None:
            break
        out.append(ev)
        if predicate(ev):
            break
    return out


def _is_done(ev: object) -> bool:
    return isinstance(ev, TurnDone)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="chat", scenario="second message queues during a streaming turn")
async def test_second_message_queues() -> None:
    release = asyncio.Event()
    orch, chat = _make_orch(_SeqProvider([_BlockingAdapter(release)]))
    conv = await chat.create_conversation(agent_key="builtin")

    first = await orch.enqueue_message(conv.id, "msg1")
    assert first is False  # started immediately
    await asyncio.sleep(0)  # let the turn task begin and block

    second = await orch.enqueue_message(conv.id, "msg2")
    assert second is True  # queued behind the in-flight turn
    assert orch.pending(conv.id) == ["msg2"]

    release.set()  # let the first turn finish so the loop can settle


@pytest.mark.acceptance(spec="chat", scenario="a queued message runs after the current turn")
async def test_queued_message_runs_after_current() -> None:
    release = asyncio.Event()
    blocking = _BlockingAdapter(release, text="first")
    quick = FakeAgentAdapter(
        [TurnStarted(), TextDelta(text="second"), TurnDone(None, None, "end_turn")]
    )
    orch, chat = _make_orch(_SeqProvider([blocking, quick]))
    conv = await chat.create_conversation(agent_key="builtin")
    sinks: list[asyncio.Queue] = []

    await orch.enqueue_message(conv.id, "msg1")
    await asyncio.sleep(0)
    await orch.enqueue_message(conv.id, "msg2", on_start=sinks.append)
    assert orch.pending(conv.id) == ["msg2"]
    assert sinks == []  # not started yet

    release.set()  # finish turn 1; the queue auto-advances to turn 2

    # The queued message's own renderer queue is attached when its turn begins.
    await asyncio.wait_for(_wait_for(lambda: bool(sinks)), 2.0)
    seen = await _collect_until(sinks[0], _is_done)
    assert any(isinstance(e, TextDelta) and e.text == "second" for e in seen)
    assert quick.recorded_prompts == ["msg2"]
    assert orch.pending(conv.id) == []


async def _wait_for(condition: Callable[[], bool]) -> None:
    while not condition():
        await asyncio.sleep(0.005)


@pytest.mark.acceptance(spec="chat", scenario="interrupting a turn pauses the pending queue")
async def test_interrupt_pauses_queue() -> None:
    release = asyncio.Event()
    orch, chat = _make_orch(_SeqProvider([_BlockingAdapter(release), FakeAgentAdapter([])]))
    conv = await chat.create_conversation(agent_key="builtin")

    await orch.enqueue_message(conv.id, "msg1")
    await asyncio.sleep(0)
    await orch.enqueue_message(conv.id, "msg2")
    assert orch.pending(conv.id) == ["msg2"]

    task = active_turns()[conv.id].task
    orch.interrupt_turn(conv.id)
    assert task is not None
    await task  # the interrupt handler ends the turn, does not re-raise
    await asyncio.sleep(0.01)  # let the advance callback run (and find the queue paused)

    # The queue is paused: msg2 was NOT auto-run.
    assert orch.pending(conv.id) == ["msg2"]


@pytest.mark.acceptance(spec="chat", scenario="the page stops a turn another surface started")
async def test_the_interrupt_route_stops_a_turn_it_did_not_start() -> None:
    """The page's Stop reaches whatever turn it is watching.

    The turn here is started through the orchestrator's queue — the path a
    channel drives — and stopped over ``POST .../interrupt``, the route the page
    calls. The route must find the turn by conversation, not by who started it.
    """
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from coffer.surfaces.http import errors as err_handlers
    from coffer.surfaces.http.auth import set_active_token
    from coffer.surfaces.http.chat.dependencies import (
        get_agent_registry,
        get_chat_service,
        get_turn_orchestrator,
    )
    from coffer.surfaces.http.chat.turn_routes import router as turn_router

    release = asyncio.Event()
    orch, chat = _make_orch(_SeqProvider([_BlockingAdapter(release), FakeAgentAdapter([])]))
    conv = await chat.create_conversation(agent_key="builtin")
    await orch.enqueue_message(conv.id, "msg1")
    await asyncio.sleep(0)
    await orch.enqueue_message(conv.id, "msg2")
    task = active_turns()[conv.id].task
    assert task is not None

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(turn_router)
    app.dependency_overrides[get_chat_service] = lambda: chat
    app.dependency_overrides[get_turn_orchestrator] = lambda: orch
    app.dependency_overrides[get_agent_registry] = lambda: orch._registry
    set_active_token("t")
    try:
        async with AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": "t"}
        ) as client:
            r = await client.post(f"/api/v1/chat/conversations/{conv.id}/interrupt")
    finally:
        set_active_token(None)

    assert r.status_code == 204, r.text
    await asyncio.wait_for(task, timeout=5)  # stopped without release being set
    await asyncio.sleep(0.01)
    assert not release.is_set()
    assert conv.id not in active_turns()
    # The queue is paused, not advanced.
    assert orch.pending(conv.id) == ["msg2"]


async def test_send_after_interrupt_resumes_queue() -> None:
    release = asyncio.Event()
    resumed = FakeAgentAdapter(
        [TurnStarted(), TextDelta(text="resumed"), TurnDone(None, None, "end_turn")]
    )
    orch, chat = _make_orch(_SeqProvider([_BlockingAdapter(release), resumed]))
    conv = await chat.create_conversation(agent_key="builtin")

    await orch.enqueue_message(conv.id, "msg1")
    await asyncio.sleep(0)
    await orch.enqueue_message(conv.id, "msg2")

    task = active_turns()[conv.id].task
    orch.interrupt_turn(conv.id)
    assert task is not None
    await task
    await asyncio.sleep(0.01)
    assert orch.pending(conv.id) == ["msg2"]  # held by the interrupt

    # A plain send unpauses and resumes the held queue (regression: previously the
    # message was appended but never drained, leaving the queue stuck).
    await orch.enqueue_message(conv.id, "msg3")
    await asyncio.wait_for(_wait_for(lambda: bool(resumed.recorded_prompts)), 2.0)
    assert resumed.recorded_prompts[0] == "msg2"
