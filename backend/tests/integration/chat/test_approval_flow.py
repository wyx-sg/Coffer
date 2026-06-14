"""Integration test: the approval route delivers a decision to a paused turn.

The built-in agent does not use the approval channel, so a fake agent provider
whose adapter requests approval proves the platform capability — exactly the
"fake test adapter" the spec calls for. A turn streams an ``approval_request``
and pauses; the real ``POST .../approvals`` route handler delivers the user's
decision and the turn resumes. The decision reaches the agent.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.application.chat.ports import ApprovalGate
from coffer.application.chat.turn_orchestrator import clear_active_turns
from coffer.domain.chat.events import (
    AgentEvent,
    ApprovalRequest,
    TextDelta,
    TurnDone,
    TurnStarted,
)
from coffer.surfaces.http.chat.schemas import ApprovalSubmit
from coffer.surfaces.http.chat.turn_routes import submit_approval
from tests.unit.chat.conftest import FakeAgentProvider, make_chat_services


class _ApprovalAdapter:
    """A fake agent whose turn requests approval, then echoes the decision."""

    model_id = None

    async def run_turn(self, *, history: Any, approvals: ApprovalGate) -> AsyncIterator[AgentEvent]:
        async def gen() -> AsyncIterator[AgentEvent]:
            yield TurnStarted()
            yield ApprovalRequest(
                request_id="req-1",
                tool_use_id="t1",
                tool_name="run_command",
                tool_input={"cmd": "ls"},
            )
            decision = await approvals.wait("req-1")
            yield TextDelta(text=f"decided:{decision.behavior}")
            yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")

        return gen()


@pytest.fixture(autouse=True)
def _reset() -> Any:
    clear_active_turns()
    yield
    clear_active_turns()


async def _drain(queue: asyncio.Queue[AgentEvent | None]) -> list[AgentEvent]:
    out: list[AgentEvent] = []
    while True:
        item = await asyncio.wait_for(queue.get(), timeout=5.0)
        if item is None:
            return out
        out.append(item)


async def _run_via_route(behavior: str) -> list[AgentEvent]:
    """Drive a turn that pauses on approval; answer it through the real route."""
    chat_svc, _model_svc, orchestrator, _registry = make_chat_services(
        provider=FakeAgentProvider(_ApprovalAdapter(), agent_key="builtin")
    )
    conv = await chat_svc.create_conversation(agent_key="builtin")

    queue = await orchestrator.start_turn(conv.id, "please run a command")

    # Drain until the turn pauses on its approval request.
    collected: list[AgentEvent] = []
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=5.0)
        assert event is not None
        collected.append(event)
        if isinstance(event, ApprovalRequest):
            break

    # Deliver the decision through the real POST .../approvals route handler.
    resp = await submit_approval(
        conv.id,
        ApprovalSubmit(request_id="req-1", behavior=behavior),
        svc=chat_svc,
        orchestrator=orchestrator,
    )
    assert resp.status_code == 204

    # The paused turn resumes; collect the rest.
    collected.extend(await _drain(queue))
    return collected


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="008-agent-chat", scenario="an agent turn pauses for human approval")
async def test_approval_allow_resumes_the_turn_via_the_route() -> None:
    events = await _run_via_route("allow")
    assert any(isinstance(e, ApprovalRequest) for e in events)
    assert any(isinstance(e, TextDelta) and e.text == "decided:allow" for e in events)
    assert any(isinstance(e, TurnDone) for e in events)


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="a denied tool call is reported to the agent"
)
async def test_approval_deny_reported_to_the_agent_via_the_route() -> None:
    events = await _run_via_route("deny")
    assert any(isinstance(e, TextDelta) and e.text == "decided:deny" for e in events)
    assert any(isinstance(e, TurnDone) for e in events)
