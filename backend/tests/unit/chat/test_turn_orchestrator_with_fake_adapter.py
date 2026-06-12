"""Unit tests for TurnOrchestrator using fake agent providers + adapters."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.chat.history import trim_history as _trim_history
from coffer.application.chat.ports import ApprovalDecision, ApprovalGate
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import (
    _ACTIVE_TURNS,
    TurnOrchestrator,
    clear_active_turns,
)
from coffer.domain.chat.events import (
    AgentEvent,
    ApprovalRequest,
    TextDelta,
    TurnDone,
    TurnError,
    TurnStarted,
)
from coffer.domain.chat.message import Message, Role, TextBlock
from coffer.domain.errors import ApprovalNotFound, NoModelConfigured, TurnInProgress

from .conftest import (
    FakeAgentAdapter,
    FakeAgentProvider,
    FakeAuditRepo,
    FakeConversationRepo,
    FakeMessageRepo,
    make_message,
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
) -> tuple[
    TurnOrchestrator, FakeConversationRepo, FakeMessageRepo, FakeAuditRepo, FakeAgentProvider
]:
    conv_repo = FakeConversationRepo()
    msg_repo = FakeMessageRepo()
    audit_repo = FakeAuditRepo()
    audit = AuditService(repo=audit_repo)  # type: ignore[arg-type]
    if adapter is None and provider is None:
        adapter = FakeAgentAdapter(events or [])
    registry, prov = make_registry(adapter=adapter, provider=provider)
    chat_svc = ChatService(
        conversations=conv_repo,
        messages=msg_repo,
        registry=registry,
        audit=audit,  # type: ignore[arg-type]
    )
    orchestrator = TurnOrchestrator(chat_service=chat_svc, registry=registry, audit=audit)
    return orchestrator, conv_repo, msg_repo, audit_repo, prov


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

    async def run_turn(self, *, history: Any, approvals: ApprovalGate) -> AsyncIterator[AgentEvent]:
        lead = self._lead

        async def gen() -> AsyncIterator[AgentEvent]:
            for ev in lead:
                yield ev
            await asyncio.sleep(3600)

        return gen()


class _ApprovalAdapter:
    """Requests approval, then echoes the decision and finishes the turn."""

    model_id = None

    def __init__(self, request_id: str = "r1") -> None:
        self._rid = request_id

    async def run_turn(self, *, history: Any, approvals: ApprovalGate) -> AsyncIterator[AgentEvent]:
        rid = self._rid

        async def gen() -> AsyncIterator[AgentEvent]:
            yield ApprovalRequest(
                request_id=rid, tool_use_id="t1", tool_name="do_thing", tool_input={"k": "v"}
            )
            decision = await approvals.wait(rid)
            yield TextDelta(text=f"decided:{decision.behavior}")
            yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")

        return gen()


@pytest.fixture(autouse=True)
def clear_turns() -> Any:
    """Ensure _ACTIVE_TURNS is clean before and after each test."""
    clear_active_turns()
    yield
    clear_active_turns()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_collects_events() -> None:
    scripted: list[AgentEvent] = [
        TurnStarted(),
        TextDelta(text="Hello"),
        TextDelta(text=" world"),
        TurnDone(prompt_tokens=10, completion_tokens=5, stop_reason="end_turn"),
    ]
    orchestrator, _conv, _msg, _audit, _prov = make_orchestrator(scripted)
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "Hi there")
    events = await drain_queue(queue)

    assert any(isinstance(e, TextDelta) for e in events)
    assert any(isinstance(e, TurnDone) for e in events)


@pytest.mark.asyncio
async def test_happy_path_persists_assistant_message() -> None:
    scripted: list[AgentEvent] = [
        TextDelta(text="Paris is the capital"),
        TurnDone(prompt_tokens=20, completion_tokens=8, stop_reason="end_turn"),
    ]
    orchestrator, _, msg_repo, _, _ = make_orchestrator(scripted)
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "What is the capital of France?")
    await drain_queue(queue)

    messages = msg_repo.all_messages()
    assert len(messages) == 2  # user + assistant
    assistant = messages[1]
    assert assistant.role == Role.ASSISTANT
    assert assistant.status == "complete"
    assert assistant.prompt_tokens == 20
    assert assistant.completion_tokens == 8
    texts = [b.text for b in assistant.content if isinstance(b, TextBlock)]
    assert "Paris is the capital" in "".join(texts)


@pytest.mark.asyncio
async def test_happy_path_emits_audit_event() -> None:
    scripted: list[AgentEvent] = [
        TurnDone(prompt_tokens=5, completion_tokens=3, stop_reason="end_turn"),
    ]
    orchestrator, _, _, audit_repo, _ = make_orchestrator(scripted)
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "ping")
    await drain_queue(queue)

    assert any(e.event_type == "chat_turn_completed" for e in audit_repo.entries)


@pytest.mark.acceptance(spec="008-agent-chat", scenario="token usage and audit")
@pytest.mark.asyncio
async def test_completed_turn_records_token_usage_and_agent_audit() -> None:
    scripted: list[AgentEvent] = [
        TextDelta(text="done"),
        TurnDone(prompt_tokens=12, completion_tokens=6, stop_reason="end_turn"),
    ]
    orchestrator, _, msg_repo, audit_repo, _ = make_orchestrator(scripted)
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "ping")
    await drain_queue(queue)

    assistant = msg_repo.all_messages()[1]
    assert assistant.prompt_tokens == 12
    assert assistant.completion_tokens == 6
    completed = next(e for e in audit_repo.entries if e.event_type == "chat_turn_completed")
    assert completed.actor == "agent"


@pytest.mark.asyncio
async def test_history_passed_to_adapter_includes_the_user_message() -> None:
    adapter = FakeAgentAdapter(
        [TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn")]
    )
    orchestrator, _, _, _, _ = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "remember this")
    await drain_queue(queue)

    assert len(adapter.recorded_histories) == 1
    history = adapter.recorded_histories[0]
    assert history[-1].role == Role.USER
    assert isinstance(history[-1].content[0], TextBlock)
    assert history[-1].content[0].text == "remember this"


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="008-agent-chat", scenario="model selection is recorded")
async def test_model_id_recorded_from_adapter() -> None:
    adapter = FakeAgentAdapter(
        [TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn")],
        model_id="m-xyz",
    )
    orchestrator, _, msg_repo, _, _ = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "hi")
    await drain_queue(queue)

    assistant = next(m for m in msg_repo.all_messages() if m.role == Role.ASSISTANT)
    assert assistant.model_id == "m-xyz"


# ---------------------------------------------------------------------------
# TurnInProgress + build_adapter errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_in_progress_raises_on_second_start() -> None:
    orchestrator, _, _, _, _ = make_orchestrator(adapter=_BlockingAdapter([]))
    conv = await orchestrator._chat.create_conversation()

    await orchestrator.start_turn(conv.id, "first message")
    with pytest.raises(TurnInProgress):
        await orchestrator.start_turn(conv.id, "second message")

    orchestrator.cancel_turn(conv.id)  # cleanup


@pytest.mark.asyncio
async def test_build_adapter_no_model_propagates_and_releases_slot() -> None:
    provider = FakeAgentProvider(adapter=None, build_error=NoModelConfigured())
    orchestrator, _, _, _, _ = make_orchestrator(provider=provider)
    conv = await orchestrator._chat.create_conversation()

    with pytest.raises(NoModelConfigured):
        await orchestrator.start_turn(conv.id, "hi")

    # The reservation was rolled back — a retry is possible.
    assert conv.id not in _ACTIVE_TURNS


# ---------------------------------------------------------------------------
# TurnError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_error_persists_failed_message() -> None:
    scripted: list[AgentEvent] = [
        TurnStarted(),
        TurnError(code="PROVIDER_ERROR", message="API rate limit exceeded"),
    ]
    orchestrator, _, msg_repo, _, _ = make_orchestrator(scripted)
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "test")
    await drain_queue(queue)

    assistants = [m for m in msg_repo.all_messages() if m.role == Role.ASSISTANT]
    assert len(assistants) == 1
    assert assistants[0].status == "failed"


# ---------------------------------------------------------------------------
# cancel_turn (delete path — discard)
# ---------------------------------------------------------------------------


class _RaisingAdapter:
    """Yields one event, then raises a non-cancellation error mid-stream."""

    model_id = None

    async def run_turn(self, *, history: Any, approvals: ApprovalGate) -> AsyncIterator[AgentEvent]:
        async def gen() -> AsyncIterator[AgentEvent]:
            yield TextDelta(text="partial")
            raise RuntimeError("boom")

        return gen()


@pytest.mark.asyncio
async def test_unexpected_adapter_error_yields_internal_error_and_failed_message() -> None:
    """An unexpected exception from the adapter surfaces as TurnError
    (INTERNAL_ERROR) and finalizes the assistant message as failed."""
    orchestrator, _, msg_repo, _, _ = make_orchestrator(adapter=_RaisingAdapter())
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "hi")
    events = await drain_queue(queue)

    errors = [e for e in events if isinstance(e, TurnError)]
    assert len(errors) == 1
    assert errors[0].code == "INTERNAL_ERROR"

    assistant = next(m for m in msg_repo.all_messages() if m.role == Role.ASSISTANT)
    assert assistant.status == "failed"
    assert conv.id not in _ACTIVE_TURNS


@pytest.mark.asyncio
async def test_cancel_turn_discards_the_partial_turn() -> None:
    orchestrator, _, msg_repo, _, _ = make_orchestrator(
        adapter=_BlockingAdapter([TextDelta(text="partial")])
    )
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "hi")
    first = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(first, TextDelta)

    orchestrator.cancel_turn(conv.id)
    await drain_queue(queue)  # returns once the sentinel arrives

    # No assistant message is persisted on the discard path.
    assert not [m for m in msg_repo.all_messages() if m.role == Role.ASSISTANT]
    assert conv.id not in _ACTIVE_TURNS


@pytest.mark.asyncio
async def test_cancel_turn_noop_when_no_active_turn() -> None:
    orchestrator, _, _, _, _ = make_orchestrator([])
    orchestrator.cancel_turn("nonexistent-conv-id")  # must not raise


# ---------------------------------------------------------------------------
# interrupt_turn (keep the partial output)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="008-agent-chat", scenario="stop a running turn")
async def test_interrupt_persists_the_partial_message() -> None:
    orchestrator, _, msg_repo, _, _ = make_orchestrator(
        adapter=_BlockingAdapter([TextDelta(text="partial answer")])
    )
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "hi")
    first = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(first, TextDelta)

    orchestrator.interrupt_turn(conv.id)
    rest = await drain_queue(queue)

    # A terminal TurnDone(stop_reason="interrupted") closes the stream.
    assert any(isinstance(e, TurnDone) and e.stop_reason == "interrupted" for e in rest)

    # The partial assistant message is persisted (status complete).
    assistant = next(m for m in msg_repo.all_messages() if m.role == Role.ASSISTANT)
    assert assistant.status == "complete"
    texts = [b.text for b in assistant.content if isinstance(b, TextBlock)]
    assert "partial answer" in "".join(texts)
    assert conv.id not in _ACTIVE_TURNS


@pytest.mark.asyncio
async def test_interrupt_noop_when_no_active_turn() -> None:
    orchestrator, _, _, _, _ = make_orchestrator([])
    orchestrator.interrupt_turn("nonexistent-conv-id")  # must not raise


# ---------------------------------------------------------------------------
# Approval relay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="008-agent-chat", scenario="an agent turn pauses for human approval")
async def test_approval_request_forwarded_and_decision_relayed() -> None:
    orchestrator, _, _, _, _ = make_orchestrator(adapter=_ApprovalAdapter("r1"))
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "do the thing")

    # The approval request reaches the stream and the turn pauses.
    event = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(event, ApprovalRequest)
    assert event.request_id == "r1"

    orchestrator.submit_approval(conv.id, "r1", ApprovalDecision(behavior="allow"))
    rest = await drain_queue(queue)

    assert any(isinstance(e, TextDelta) and e.text == "decided:allow" for e in rest)
    assert any(isinstance(e, TurnDone) for e in rest)


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="a denied tool call is reported to the agent"
)
async def test_approval_deny_decision_is_relayed_to_the_agent() -> None:
    orchestrator, _, _, _, _ = make_orchestrator(adapter=_ApprovalAdapter("r1"))
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "do the thing")
    event = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(event, ApprovalRequest)

    orchestrator.submit_approval(conv.id, "r1", ApprovalDecision(behavior="deny"))
    rest = await drain_queue(queue)

    # The denial is delivered to the agent, which proceeds without the tool.
    assert any(isinstance(e, TextDelta) and e.text == "decided:deny" for e in rest)
    assert any(isinstance(e, TurnDone) for e in rest)


@pytest.mark.asyncio
async def test_submit_approval_no_active_turn_raises() -> None:
    orchestrator, _, _, _, _ = make_orchestrator([])
    with pytest.raises(ApprovalNotFound):
        orchestrator.submit_approval("no-conv", "r1", ApprovalDecision(behavior="allow"))


@pytest.mark.asyncio
async def test_submit_approval_unknown_request_raises() -> None:
    orchestrator, _, _, _, _ = make_orchestrator(adapter=_ApprovalAdapter("r1"))
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "do the thing")
    await asyncio.wait_for(queue.get(), timeout=5.0)  # the ApprovalRequest

    with pytest.raises(ApprovalNotFound):
        orchestrator.submit_approval(conv.id, "wrong-id", ApprovalDecision(behavior="allow"))

    orchestrator.interrupt_turn(conv.id)  # cleanup
    await drain_queue(queue)


@pytest.mark.asyncio
async def test_interrupt_while_waiting_for_approval_ends_the_turn() -> None:
    """Interrupting a turn parked in approvals.wait() cancels the wait and the
    turn ends with a terminal TurnDone(stop_reason='interrupted')."""
    orchestrator, _, _, _, _ = make_orchestrator(adapter=_ApprovalAdapter("r1"))
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "do the thing")
    event = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(event, ApprovalRequest)

    # Interrupt while the turn is parked inside approvals.wait().
    orchestrator.interrupt_turn(conv.id)
    rest = await drain_queue(queue)

    assert any(isinstance(e, TurnDone) and e.stop_reason == "interrupted" for e in rest)
    assert conv.id not in _ACTIVE_TURNS


# ---------------------------------------------------------------------------
# Active-turn registry hygiene
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_turns_cleared_after_completion() -> None:
    scripted: list[AgentEvent] = [
        TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn"),
    ]
    orchestrator, _, _, _, _ = make_orchestrator(scripted)
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "hi")
    await drain_queue(queue)

    assert conv.id not in _ACTIVE_TURNS


# ---------------------------------------------------------------------------
# Placeholder edge cases: early failure, cancel-during-append
# ---------------------------------------------------------------------------


class _PlaceholderFailRepo(FakeMessageRepo):
    """Raises on the streaming-placeholder append; everything else works."""

    async def append(self, message: Any) -> Any:
        if message.status == "streaming":
            raise RuntimeError("db down")
        return await super().append(message)


@pytest.mark.asyncio
async def test_placeholder_write_failure_still_persists_failed_message_and_audit() -> None:
    """If the placeholder write itself fails, the turn must still leave a
    persisted failed assistant message and a CHAT_TURN_COMPLETED audit record
    (not vanish from the trail)."""
    conv_repo = FakeConversationRepo()
    msg_repo = _PlaceholderFailRepo()
    audit_repo = FakeAuditRepo()
    audit = AuditService(repo=audit_repo)  # type: ignore[arg-type]
    adapter = FakeAgentAdapter(
        [TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn")]
    )
    registry, _ = make_registry(adapter=adapter)
    chat_svc = ChatService(
        conversations=conv_repo, messages=msg_repo, registry=registry, audit=audit
    )  # type: ignore[arg-type]
    orchestrator = TurnOrchestrator(chat_service=chat_svc, registry=registry, audit=audit)
    conv = await chat_svc.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "hi")
    events = await drain_queue(queue)

    # The client sees a TurnError…
    assert any(isinstance(e, TurnError) and e.code == "INTERNAL_ERROR" for e in events)
    # …and the failure is persisted + audited, not silently dropped.
    assistants = [m for m in msg_repo.all_messages() if m.role == Role.ASSISTANT]
    assert len(assistants) == 1
    assert assistants[0].status == "failed"
    assert any(e.event_type == "chat_turn_completed" for e in audit_repo.entries)


class _SlowPlaceholderRepo(FakeMessageRepo):
    """Parks the streaming-placeholder append on a gate (simulating an INSERT
    whose surrounding awaits outlive a cancellation)."""

    def __init__(self) -> None:
        super().__init__()
        self.gate = asyncio.Event()

    async def append(self, message: Any) -> Any:
        if message.status == "streaming":
            await self.gate.wait()
        return await super().append(message)


@pytest.mark.asyncio
async def test_interrupt_during_placeholder_append_leaves_no_orphan_streaming_row() -> None:
    """An interrupt that lands while the placeholder append is still in flight
    must recover the committed row and finalize it — no orphan streaming row."""
    conv_repo = FakeConversationRepo()
    msg_repo = _SlowPlaceholderRepo()
    audit_repo = FakeAuditRepo()
    audit = AuditService(repo=audit_repo)  # type: ignore[arg-type]
    adapter = FakeAgentAdapter(
        [TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn")]
    )
    registry, _ = make_registry(adapter=adapter)
    chat_svc = ChatService(
        conversations=conv_repo, messages=msg_repo, registry=registry, audit=audit
    )  # type: ignore[arg-type]
    orchestrator = TurnOrchestrator(chat_service=chat_svc, registry=registry, audit=audit)
    conv = await chat_svc.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "hi")
    await asyncio.sleep(0)  # let the task reach the parked append

    orchestrator.interrupt_turn(conv.id)
    msg_repo.gate.set()  # the in-flight append completes after the cancel
    events = await drain_queue(queue)

    assert any(isinstance(e, TurnDone) and e.stop_reason == "interrupted" for e in events)
    assistants = [m for m in msg_repo.all_messages() if m.role == Role.ASSISTANT]
    assert len(assistants) == 1
    assert assistants[0].status != "streaming"  # recovered + finalized, not orphaned


@pytest.mark.asyncio
async def test_turn_completion_bumps_conversation_updated_at() -> None:
    """Finalizing a turn must refresh the conversation's updated_at so the
    recency-ordered conversation list reflects turn *completion*, not just the
    turn-start writes (user message + placeholder)."""
    orchestrator, conv_repo, _, _, _ = make_orchestrator(
        adapter=_BlockingAdapter([TextDelta(text="partial")])
    )
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "hi")
    # First event means the placeholder row (and its touch) already happened.
    first = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(first, TextDelta)
    mid_turn = await conv_repo.get(conv.id)
    assert mid_turn is not None

    orchestrator.interrupt_turn(conv.id)
    await drain_queue(queue)

    finished = await conv_repo.get(conv.id)
    assert finished is not None
    assert finished.updated_at > mid_turn.updated_at


# ---------------------------------------------------------------------------
# Startup sweep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_flight_turn_leaves_a_streaming_assistant_row() -> None:
    """While a turn streams, a placeholder assistant message with
    status='streaming' must exist, so a daemon crash leaves a row the startup
    sweep can flip to 'failed' (FR-022) rather than a silently-missing reply."""
    orchestrator, _, msg_repo, _, _ = make_orchestrator(
        adapter=_BlockingAdapter([TextDelta(text="partial")])
    )
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "hi")
    first = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(first, TextDelta)

    assistants = [m for m in msg_repo.all_messages() if m.role == Role.ASSISTANT]
    assert len(assistants) == 1
    assert assistants[0].status == "streaming"

    orchestrator.cancel_turn(conv.id)  # cleanup
    await drain_queue(queue)


@pytest.mark.asyncio
async def test_completed_turn_finalizes_the_same_row_not_a_duplicate() -> None:
    """A completed turn finalizes the streaming placeholder in place — exactly
    one assistant message, no duplicate row."""
    scripted: list[AgentEvent] = [
        TextDelta(text="done"),
        TurnDone(prompt_tokens=3, completion_tokens=2, stop_reason="end_turn"),
    ]
    orchestrator, _, msg_repo, _, _ = make_orchestrator(scripted)
    conv = await orchestrator._chat.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "hi")
    await drain_queue(queue)

    assistants = [m for m in msg_repo.all_messages() if m.role == Role.ASSISTANT]
    assert len(assistants) == 1
    assert assistants[0].status == "complete"


@pytest.mark.asyncio
async def test_sweep_streaming_flips_streaming_to_failed() -> None:
    msg_repo = FakeMessageRepo()
    msg_repo._messages = [
        make_message(0, "partial", status="streaming"),
        make_message(1, "done", status="complete"),
        make_message(2, "partial", status="streaming"),
    ]

    count = await TurnOrchestrator.sweep_streaming_messages(msg_repo)  # type: ignore[arg-type]
    assert count == 2
    statuses = [m.status for m in msg_repo._messages]
    assert statuses.count("failed") == 2
    assert "streaming" not in statuses


# ---------------------------------------------------------------------------
# History trimming (pure function)
# ---------------------------------------------------------------------------


def test_trim_history_no_truncation_when_messages_fit() -> None:
    msgs: list[Message] = [make_message(i, "hi") for i in range(3)]
    kept, truncated = _trim_history(msgs, char_budget=1_000_000)
    assert len(kept) == 3
    assert truncated is False


def test_trim_history_truncation_when_messages_exceed_budget() -> None:
    msgs: list[Message] = [make_message(i, "x" * 20) for i in range(5)]
    kept, truncated = _trim_history(msgs, char_budget=45)
    assert len(kept) < 5
    assert truncated is True
    assert kept[-1].id == "msg-4"  # the most recent message is always kept
