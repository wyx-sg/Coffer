"""Human-in-the-loop confirmation flow (spec 008-builtin-agent-chat)."""

from __future__ import annotations

import pytest

from coffer.domain.chat.runtime import ConfirmationRequest, DoneEvent, ToolResultEvent
from tests.integration.chat.fakes import FakeRuntime

SPEC = "008-builtin-agent-chat"


def _confirm_runtime() -> FakeRuntime:
    return FakeRuntime([ConfirmationRequest(id="c1", tool="coffer__delete_memory", args={"id": 3})])


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat", scenario="sensitive tool use pauses for confirmation"
)
async def test_sensitive_tool_pauses_for_confirmation(chat_env):
    chat_env.factory.runtime = _confirm_runtime()
    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    gen = await chat_env.chat.send(conv.id, "forget fact 3")
    first = await gen.__anext__()
    assert isinstance(first, ConfirmationRequest)
    assert first.tool == "coffer__delete_memory"
    # Turn is suspended awaiting a decision.
    assert chat_env.chat.has_active_turn(conv.id)
    # Resolve so the fixture teardown isn't left with a parked turn.
    await chat_env.chat.resolve_confirmation(conv.id, first.id, True)
    rest = [ev async for ev in gen]
    assert isinstance(rest[-1], DoneEvent)


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat",
    scenario="approving a confirmation runs the tool and resumes the turn",
)
async def test_approving_confirmation_runs_tool(chat_env):
    chat_env.factory.runtime = _confirm_runtime()
    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    gen = await chat_env.chat.send(conv.id, "forget fact 3")
    seen = []
    async for ev in gen:
        seen.append(ev)
        if isinstance(ev, ConfirmationRequest):
            await chat_env.chat.resolve_confirmation(conv.id, ev.id, True)
    results = [e for e in seen if isinstance(e, ToolResultEvent)]
    assert len(results) == 1 and results[0].ok is True
    assert isinstance(seen[-1], DoneEvent)
    assistant = (await chat_env.chat.get_messages(conv.id))[-1]
    assert assistant.tool_calls[0].confirmed is True
    assert assistant.tool_calls[0].result_summary == "ran"


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat",
    scenario="denying a confirmation skips the tool and informs the agent",
)
async def test_denying_confirmation_skips_tool(chat_env):
    chat_env.factory.runtime = _confirm_runtime()
    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    gen = await chat_env.chat.send(conv.id, "forget fact 3")
    seen = []
    async for ev in gen:
        seen.append(ev)
        if isinstance(ev, ConfirmationRequest):
            await chat_env.chat.resolve_confirmation(conv.id, ev.id, False)
    results = [e for e in seen if isinstance(e, ToolResultEvent)]
    assert len(results) == 1 and results[0].ok is False
    assert isinstance(seen[-1], DoneEvent)  # turn ends without error
    assistant = (await chat_env.chat.get_messages(conv.id))[-1]
    assert assistant.tool_calls[0].confirmed is False
    assert "declined" in assistant.tool_calls[0].result_summary
