"""A turn's records carry its conversation and turn ids (spec resource-framework
"Correlate the audit log, the MCP invocation log and the daemon log by one
trace id").

The adapter here audits one event from inside the turn, the way a turn's own
work does, and records the correlation it saw; the audit row the service files
is read back off the fake repo.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.runtime import correlation
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone
from tests.support.chat_turns import start_turn

from .conftest import FakeAuditRepo, FakeConversationRepo, make_registry


class _AuditingAdapter:
    """Audits one event mid-turn and remembers the correlation it ran under."""

    model_id = None

    def __init__(self, audit: AuditService) -> None:
        self._audit = audit
        self.seen: list[correlation.Correlation] = []

    async def run_turn(
        self, prompt: str, attachments: Sequence[Any] = ()
    ) -> AsyncIterator[AgentEvent]:
        return self._events()

    async def _events(self) -> AsyncIterator[AgentEvent]:
        self.seen.append(correlation.current())
        await self._audit.record("memory_delivery_fired", actor="agent")
        yield TextDelta(text="ok")
        yield TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn")


async def _run_one_turn(orchestrator: TurnOrchestrator, conversation_id: str) -> None:
    queue = await start_turn(orchestrator, conversation_id, "hi")
    while await asyncio.wait_for(queue.get(), timeout=5.0) is not None:
        pass


def _orchestrator(audit: AuditService) -> tuple[TurnOrchestrator, _AuditingAdapter]:
    adapter = _AuditingAdapter(audit)
    registry, _prov = make_registry(adapter=adapter)
    chat = ChatService(conversations=FakeConversationRepo(), registry=registry)
    return TurnOrchestrator(chat_service=chat, registry=registry), adapter


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a turn's records carry its conversation and turn"
)
async def test_a_turns_audit_row_carries_its_conversation_and_turn() -> None:
    repo = FakeAuditRepo()
    orchestrator, adapter = _orchestrator(AuditService(repo))
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    correlation.bind_trace_id(None)  # a channel turn: no HTTP request behind it
    await _run_one_turn(orchestrator, conv.id)
    await _run_one_turn(orchestrator, conv.id)

    first, second = repo.entries
    assert first.conversation_id == second.conversation_id == conv.id
    assert first.turn_id and second.turn_id and first.turn_id != second.turn_id
    # With no request behind the turn, the turn's own id is the trace id.
    assert first.trace_id == first.turn_id
    assert adapter.seen[0].log_fields()["turn_id"] == first.turn_id
    # The caller's context is left as it was.
    assert correlation.current() == correlation.Correlation()


async def test_a_turn_started_by_a_request_keeps_the_requests_trace_id() -> None:
    repo = FakeAuditRepo()
    orchestrator, _adapter = _orchestrator(AuditService(repo))
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    with correlation.correlated(trace_id="req-42"):
        await _run_one_turn(orchestrator, conv.id)

    [entry] = repo.entries
    assert entry.trace_id == "req-42"
    assert entry.conversation_id == conv.id
    assert entry.turn_id is not None and entry.turn_id != "req-42"
