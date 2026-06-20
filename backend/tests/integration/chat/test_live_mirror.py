"""Live-mirror + pending-queue behaviour (ADR-031), tested at the orchestrator
level where turn timing is deterministic.

A turn runs as a detached task and publishes to a per-conversation bus, so the
deep behaviours (live observation, FIFO queueing, interrupt-pauses-queue,
cross-surface observation) are exercised here by subscribing to the bus and
driving a controllable adapter, rather than through the sync TestClient (which
cannot observe a detached task nor hold the long-lived GET .../events stream).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import (
    TurnOrchestrator,
    active_turns,
    clear_active_turns,
)
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from coffer.domain.chat.message import Message
from tests.unit.chat.conftest import (
    FakeAgentAdapter,
    FakeAuditRepo,
    FakeConversationRepo,
    FakeMessageRepo,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_active_turns()
    yield
    clear_active_turns()


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
        adapter = self._adapters[self.builds]
        self.builds += 1
        return adapter

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

    async def run_turn(self, *, history: Sequence[Message]) -> AsyncIterator[AgentEvent]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[AgentEvent]:
        yield TurnStarted()
        yield TextDelta(text=self._text)
        await self._release.wait()
        yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


def _make_orch(provider: object) -> tuple[TurnOrchestrator, ChatService, FakeMessageRepo]:
    audit = AuditService(repo=FakeAuditRepo())  # type: ignore[arg-type]
    conv_repo = FakeConversationRepo()
    msg_repo = FakeMessageRepo()
    registry = AgentProviderRegistry()
    registry.register(provider, display_name="Coffer Assistant")  # type: ignore[arg-type]
    chat = ChatService(
        conversations=conv_repo,
        messages=msg_repo,
        registry=registry,
        audit=audit,  # type: ignore[arg-type]
    )
    orch = TurnOrchestrator(chat_service=chat, registry=registry, audit=audit)
    return orch, chat, msg_repo


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


@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="send a message and receive a streamed reply"
)
async def test_streamed_reply_over_subscription() -> None:
    adapter = FakeAgentAdapter(
        [TurnStarted(), TextDelta(text="Hello!"), TurnDone(None, None, "end_turn")]
    )
    orch, chat, _ = _make_orch(_SeqProvider([adapter]))
    conv = await chat.create_conversation(agent_key="builtin")

    q = orch.subscribe(conv.id)
    queued = await orch.enqueue_message(conv.id, "hi")
    assert queued is False

    events = await _collect_until(q, _is_done)
    types = [e.type for e in events]  # type: ignore[attr-defined]
    assert "turn_start" in types
    assert "text_delta" in types
    assert "turn_done" in types


@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="observe a turn started from another surface"
)
async def test_observe_turn_from_another_surface() -> None:
    adapter = FakeAgentAdapter(
        [TurnStarted(), TextDelta(text="from-channel"), TurnDone(None, None, "end_turn")]
    )
    orch, chat, _ = _make_orch(_SeqProvider([adapter]))
    conv = await chat.create_conversation(agent_key="builtin")

    # A web observer subscribes; the turn is started via the channel seam.
    observer = orch.subscribe(conv.id)
    await orch.start_turn(conv.id, "hi from IM")

    events = await _collect_until(observer, _is_done)
    texts = [e.text for e in events if isinstance(e, TextDelta)]
    assert "from-channel" in texts


@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="second message queues during a streaming turn"
)
async def test_second_message_queues() -> None:
    release = asyncio.Event()
    orch, chat, _ = _make_orch(_SeqProvider([_BlockingAdapter(release)]))
    conv = await chat.create_conversation(agent_key="builtin")

    first = await orch.enqueue_message(conv.id, "msg1")
    assert first is False  # started immediately
    await asyncio.sleep(0)  # let the turn task begin and block

    second = await orch.enqueue_message(conv.id, "msg2")
    assert second is True  # queued behind the in-flight turn
    assert orch.pending(conv.id) == ["msg2"]

    release.set()  # let the first turn finish so the loop can settle


@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="a queued message runs after the current turn"
)
async def test_queued_message_runs_after_current() -> None:
    release = asyncio.Event()
    blocking = _BlockingAdapter(release, text="first")
    quick = FakeAgentAdapter(
        [TurnStarted(), TextDelta(text="second"), TurnDone(None, None, "end_turn")]
    )
    orch, chat, msg_repo = _make_orch(_SeqProvider([blocking, quick]))
    conv = await chat.create_conversation(agent_key="builtin")

    observer = orch.subscribe(conv.id)
    await orch.enqueue_message(conv.id, "msg1")
    await asyncio.sleep(0)
    await orch.enqueue_message(conv.id, "msg2")
    assert orch.pending(conv.id) == ["msg2"]

    release.set()  # finish turn 1; the queue auto-advances to turn 2

    # Observe both turns complete over the same subscription.
    seen_second = await _collect_until(
        observer, lambda e: isinstance(e, TextDelta) and e.text == "second"
    )
    assert any(isinstance(e, TextDelta) and e.text == "second" for e in seen_second)
    assert orch.pending(conv.id) == []
    # Both user messages were committed in order.
    user_texts = [
        b.text
        for m in msg_repo.all_messages()
        if m.role.value == "user"
        for b in m.content
        if b.type == "text"
    ]
    assert user_texts == ["msg1", "msg2"]


@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="interrupting a turn pauses the pending queue"
)
async def test_interrupt_pauses_queue() -> None:
    release = asyncio.Event()
    orch, chat, _ = _make_orch(_SeqProvider([_BlockingAdapter(release), FakeAgentAdapter([])]))
    conv = await chat.create_conversation(agent_key="builtin")

    await orch.enqueue_message(conv.id, "msg1")
    await asyncio.sleep(0)
    await orch.enqueue_message(conv.id, "msg2")
    assert orch.pending(conv.id) == ["msg2"]

    task = active_turns()[conv.id].task
    orch.interrupt_turn(conv.id)
    assert task is not None
    await task  # interrupt handler persists the partial, does not re-raise
    await asyncio.sleep(0.01)  # let the advance callback run (and find the queue paused)

    # The queue is paused: msg2 was NOT auto-run.
    assert orch.pending(conv.id) == ["msg2"]


@pytest.mark.acceptance(spec="008-agent-chat", scenario="reply survives a restart")
async def test_reply_persisted() -> None:
    adapter = FakeAgentAdapter(
        [TurnStarted(), TextDelta(text="Hello, world!"), TurnDone(12, 6, "end_turn")]
    )
    orch, chat, _ = _make_orch(_SeqProvider([adapter]))
    conv = await chat.create_conversation(agent_key="builtin")

    q = orch.subscribe(conv.id)
    await orch.enqueue_message(conv.id, "Tell me something")
    await _collect_until(q, _is_done)

    msgs = await chat.list_messages(conv.id)
    assert len(msgs) == 2
    assistant = next(m for m in msgs if m.role.value == "assistant")
    assert assistant.status == "complete"
    text = "".join(b.text for b in assistant.content if b.type == "text")
    assert text == "Hello, world!"


async def test_queue_changed_broadcast_to_subscribers() -> None:
    release = asyncio.Event()
    orch, chat, _ = _make_orch(_SeqProvider([_BlockingAdapter(release)]))
    conv = await chat.create_conversation(agent_key="builtin")

    q = orch.subscribe(conv.id)
    await orch.enqueue_message(conv.id, "msg1")
    await asyncio.sleep(0)
    await orch.enqueue_message(conv.id, "msg2")

    # The subscriber receives a queue_changed event reflecting ["msg2"].
    pendings = []
    for _ in range(20):
        try:
            ev = q.get_nowait()
        except asyncio.QueueEmpty:
            break
        if ev is not None and ev.type == "queue_changed":
            pendings.append(ev.pending)
    assert ["msg2"] in pendings
    release.set()
