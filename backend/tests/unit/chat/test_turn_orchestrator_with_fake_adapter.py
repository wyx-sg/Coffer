"""Unit tests for TurnOrchestrator using fake agent providers + adapters."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import (
    TurnOrchestrator,
    active_turns,
)
from coffer.application.chat.turn_state import peek
from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.errors import AgentConfigRejected
from coffer.domain.chat.events import (
    AgentEvent,
    TextDelta,
    TurnDone,
    TurnError,
    TurnStarted,
)
from tests.support.chat_turns import start_turn

from .conftest import (
    FakeAgentAdapter,
    FakeAgentProvider,
    FakeConversationRepo,
    make_registry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_orchestrator(
    events: list[AgentEvent] | None = None,
    *,
    adapter: Any = None,
    provider: Any = None,
) -> tuple[TurnOrchestrator, FakeConversationRepo, FakeAgentProvider]:
    conv_repo = FakeConversationRepo()
    if adapter is None and provider is None:
        adapter = FakeAgentAdapter(events or [])
    registry, prov = make_registry(adapter=adapter, provider=provider)
    chat_svc = ChatService(conversations=conv_repo, registry=registry)
    orchestrator = TurnOrchestrator(chat_service=chat_svc, registry=registry)
    return orchestrator, conv_repo, prov


async def drain_queue(queue: asyncio.Queue[AgentEvent | None]) -> list[AgentEvent]:
    """Collect events until the end-of-stream ``None`` sentinel."""
    events: list[AgentEvent] = []
    while True:
        item = await asyncio.wait_for(queue.get(), timeout=5.0)
        if item is None:
            break
        events.append(item)
    return events


class _BlockingAdapter:
    """Emits a few lead events, then blocks until the turn task is cancelled."""

    def __init__(self, lead: list[AgentEvent], *, model_id: str | None = None) -> None:
        self._lead = lead
        self.model_id = model_id

    async def run_turn(self, prompt: str, attachments: Any = ()) -> AsyncIterator[AgentEvent]:
        lead = self._lead

        async def gen() -> AsyncIterator[AgentEvent]:
            for ev in lead:
                yield ev
            await asyncio.sleep(3600)

        return gen()


_DONE = TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn")

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="chat", scenario="a turn streams its typed events in order and stores none of them"
)
async def test_happy_path_collects_events() -> None:
    scripted: list[AgentEvent] = [
        TurnStarted(),
        TextDelta(text="Hello"),
        TextDelta(text=" world"),
        TurnDone(prompt_tokens=10, completion_tokens=5, stop_reason="end_turn"),
    ]
    orchestrator, _conv, _prov = make_orchestrator(scripted)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "Hi there")
    events = await drain_queue(queue)

    assert any(isinstance(e, TextDelta) for e in events)
    assert any(isinstance(e, TurnDone) for e in events)
    # The renderer got the turn's events in the order the adapter produced them.
    assert events == scripted
    # Nothing of the turn's text was written: the index row is the only record.
    stored = await _conv.get(conv.id)
    assert stored is not None
    assert "Hello" not in repr(stored)


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="chat", scenario="the orchestrator hands an adapter only the turn")
async def test_the_adapter_is_given_the_prompt_and_the_attachments() -> None:
    adapter = FakeAgentAdapter([_DONE])
    orchestrator, _, _ = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    image = Attachment(path="/tmp/coffer-media/a.jpg", mime="image/jpeg", filename="a.jpg")

    await drain_queue(await start_turn(orchestrator, conv.id, "remember this", attachments=[image]))

    assert adapter.recorded_prompts == ["remember this"]
    assert adapter.recorded_attachments == [[image]]


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="chat", scenario="a turn carries no history")
async def test_a_later_turn_is_given_only_its_own_message() -> None:
    adapter = FakeAgentAdapter([_DONE])
    orchestrator, _, provider = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    await drain_queue(await start_turn(orchestrator, conv.id, "first question"))
    await drain_queue(await start_turn(orchestrator, conv.id, "second question"))

    # Each turn is its message and nothing earlier; the adapter is built from the
    # conversation id alone, so it resumes the stored native session itself.
    assert adapter.recorded_prompts == ["first question", "second question"]
    assert all("first question" not in p for p in adapter.recorded_prompts[1:])
    assert adapter.recorded_attachments == [[], []]
    assert provider.init_calls and provider.deleted == []


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="chat", scenario="a completed turn is not replayed")
async def test_a_completed_turn_leaves_nothing_to_replay() -> None:
    scripted: list[AgentEvent] = [TurnStarted(), TextDelta(text="secret reply"), _DONE]
    orchestrator, _, _ = make_orchestrator(scripted)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    await drain_queue(await start_turn(orchestrator, conv.id, "go"))
    await asyncio.sleep(0)

    # What a late subscriber could read: the pending-queue snapshot (empty), and no
    # turn in flight or held with the turn's content.
    assert orchestrator.pending(conv.id) == []
    assert conv.id not in active_turns()
    state = peek(conv.id)
    assert state is None or (state.active is None and state.queue == [])


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="chat", scenario="a reported model reaches the turn's log line")
async def test_a_reported_model_reaches_the_turn_log_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    scripted: list[AgentEvent] = [TurnStarted(), TextDelta(text="hi"), _DONE]
    orchestrator, _, _ = make_orchestrator(adapter=FakeAgentAdapter(scripted, model_id="model-x"))
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    with caplog.at_level("INFO", logger="coffer.application.chat.turn_runner"):
        await drain_queue(await start_turn(orchestrator, conv.id, "go"))
    assert any("model-x" in r.getMessage() for r in caplog.records)

    # An adapter that names no model (no attribute at all) is still a valid adapter.
    class _NoModel:
        async def run_turn(self, prompt: str, attachments: Any = ()) -> AsyncIterator[AgentEvent]:
            async def gen() -> AsyncIterator[AgentEvent]:
                for ev in scripted:
                    yield ev

            return gen()

    orchestrator2, _, _ = make_orchestrator(adapter=_NoModel())
    conv2 = await orchestrator2._chat.create_conversation(agent_key="builtin")
    events = await drain_queue(await start_turn(orchestrator2, conv2.id, "go"))
    assert isinstance(events[-1], TurnDone)


@pytest.mark.asyncio
async def test_a_turn_names_its_conversation_after_the_first_words_and_bumps_it() -> None:
    orchestrator, conv_repo, _ = make_orchestrator([_DONE])
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")
    assert conv.title == "New conversation"

    await drain_queue(await start_turn(orchestrator, conv.id, "plan the offsite"))

    named = await conv_repo.get(conv.id)
    assert named is not None
    assert named.title == "plan the offsite"
    assert named.updated_at > conv.updated_at


# ---------------------------------------------------------------------------
# build_adapter errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_adapter_error_propagates_and_releases_slot() -> None:
    err = AgentConfigRejected("missing_secret", "agent could not build its adapter")
    provider = FakeAgentProvider(adapter=None, build_error=err)
    orchestrator, _, _ = make_orchestrator(provider=provider)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    with pytest.raises(AgentConfigRejected):
        await start_turn(orchestrator, conv.id, "hi")

    # The reservation was rolled back — a retry is possible.
    assert conv.id not in active_turns()


# ---------------------------------------------------------------------------
# TurnError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_error_is_logged_server_side(caplog: pytest.LogCaptureFixture) -> None:
    """A turn that ends in a TurnError must leave a server-side log trace —
    the event alone disappears with the renderer."""
    scripted: list[AgentEvent] = [
        TurnStarted(),
        TurnError(code="PROVIDER_ERROR", message="API rate limit exceeded"),
    ]
    orchestrator, _, _ = make_orchestrator(scripted)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    with caplog.at_level("WARNING", logger="coffer.application.chat.turn_runner"):
        queue = await start_turn(orchestrator, conv.id, "test")
        await drain_queue(queue)

    records = [r for r in caplog.records if "PROVIDER_ERROR" in r.getMessage()]
    assert records, "expected a WARNING log naming the turn error code"
    assert "API rate limit exceeded" in records[0].getMessage()


class _RaisingAdapter:
    """Yields one event, then raises a non-cancellation error mid-stream."""

    model_id = None

    async def run_turn(self, prompt: str, attachments: Any = ()) -> AsyncIterator[AgentEvent]:
        async def gen() -> AsyncIterator[AgentEvent]:
            yield TextDelta(text="partial")
            raise RuntimeError("boom")

        return gen()


@pytest.mark.asyncio
async def test_unexpected_adapter_error_yields_internal_error() -> None:
    """An unexpected exception from the adapter surfaces as TurnError
    (INTERNAL_ERROR) and the turn's slot is released."""
    orchestrator, _, _ = make_orchestrator(adapter=_RaisingAdapter())
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    events = await drain_queue(queue)

    errors = [e for e in events if isinstance(e, TurnError)]
    assert len(errors) == 1
    assert errors[0].code == "INTERNAL_ERROR"
    assert conv.id not in active_turns()


# ---------------------------------------------------------------------------
# cancel_turn (delete path — discard)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_turn_discards_the_turn_without_a_terminal_event() -> None:
    orchestrator, _, _ = make_orchestrator(adapter=_BlockingAdapter([TextDelta(text="partial")]))
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    first = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(first, TextDelta)

    orchestrator.cancel_turn(conv.id)
    rest = await drain_queue(queue)  # returns once the sentinel arrives

    # A deleted conversation's turn ends silently.
    assert not [e for e in rest if isinstance(e, (TurnDone, TurnError))]
    assert conv.id not in active_turns()


@pytest.mark.asyncio
async def test_cancel_turn_noop_when_no_active_turn() -> None:
    orchestrator, _, _ = make_orchestrator([])
    orchestrator.cancel_turn("nonexistent-conv-id")  # must not raise


# ---------------------------------------------------------------------------
# interrupt_turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="chat", scenario="stop a running turn")
async def test_interrupt_ends_the_turn_as_interrupted() -> None:
    orchestrator, _, _ = make_orchestrator(
        adapter=_BlockingAdapter([TextDelta(text="partial answer")])
    )
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    first = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(first, TextDelta)

    orchestrator.interrupt_turn(conv.id)
    rest = await drain_queue(queue)

    # A terminal TurnDone(stop_reason="interrupted") closes the stream.
    assert any(isinstance(e, TurnDone) and e.stop_reason == "interrupted" for e in rest)
    assert conv.id not in active_turns()


@pytest.mark.asyncio
async def test_interrupt_noop_when_no_active_turn() -> None:
    orchestrator, _, _ = make_orchestrator([])
    orchestrator.interrupt_turn("nonexistent-conv-id")  # must not raise


# ---------------------------------------------------------------------------
# Active-turn registry hygiene
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_turns_cleared_after_completion() -> None:
    orchestrator, _, _ = make_orchestrator([_DONE])
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    await drain_queue(queue)

    assert conv.id not in active_turns()


@pytest.mark.asyncio
async def test_turn_completion_bumps_conversation_updated_at() -> None:
    """Ending a turn refreshes the conversation's updated_at so the
    recency-ordered conversation list reflects turn *completion*, not just the
    turn start."""
    orchestrator, conv_repo, _ = make_orchestrator(
        adapter=_BlockingAdapter([TextDelta(text="partial")])
    )
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    first = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(first, TextDelta)
    mid_turn = await conv_repo.get(conv.id)
    assert mid_turn is not None

    orchestrator.interrupt_turn(conv.id)
    await drain_queue(queue)

    finished = await conv_repo.get(conv.id)
    assert finished is not None
    assert finished.updated_at > mid_turn.updated_at
