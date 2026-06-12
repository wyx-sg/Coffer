"""Approval prompts cross the channel: agent gate ⇄ IM buttons ⇄ decision.

Mirrors the spec-008 approval-flow test: a scripted agent pauses on
``approvals.wait`` and the decision travels through the real InboundProcessor
(``on_approval_click``) instead of the HTTP route.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.domain.channel.envelopes import ApprovalClick
from coffer.domain.chat.events import (
    AgentEvent,
    ApprovalRequest,
    TextDelta,
    TurnDone,
    TurnStarted,
)

from .conftest import ChannelEnv, inbound, wait_until


class ApprovalAgentAdapter:
    """Requests approval for one tool call, then echoes the decision."""

    model_id = None

    def __init__(self) -> None:
        self.decisions: list[str] = []

    async def run_turn(self, *, history: Any, approvals: Any) -> AsyncIterator[AgentEvent]:
        async def gen() -> AsyncIterator[AgentEvent]:
            yield TurnStarted()
            yield ApprovalRequest(
                request_id="req-1",
                tool_use_id="t1",
                tool_name="run_command",
                tool_input={"cmd": "rm -rf ./build"},
            )
            decision = await approvals.wait("req-1")
            self.decisions.append(decision.behavior)
            yield TextDelta(text=f"decided:{decision.behavior}")
            yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")

        return gen()


@pytest.mark.acceptance(
    spec="009-channels", scenario="an approval prompt is answered from the IM chat"
)
async def test_allow_click_resolves_the_gate_and_the_turn_continues(env: ChannelEnv) -> None:
    agent = ApprovalAgentAdapter()
    env.provider.adapter = agent
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "clean the build dir"))
    await wait_until(lambda: adapter.approval_prompts)

    assert len(adapter.approval_prompts) == 1
    prompt = adapter.approval_prompts[0]
    assert prompt.chat_id == "owner"
    assert prompt.text.startswith("🔐 Approval required: run_command")
    assert "rm -rf ./build" in prompt.text
    assert prompt.allow_value == "req-1|allow"
    assert prompt.deny_value == "req-1|deny"

    await env.processor.on_approval_click(
        ApprovalClick(
            channel="tg",
            chat_id="owner",
            value="req-1|allow",
            prompt_message_id=prompt.message_id,
        )
    )

    await wait_until(lambda: "decided:allow" in adapter.texts())
    assert agent.decisions == ["allow"]  # the agent received the decision
    assert adapter.resolved == [("owner", prompt.message_id, "✅ Approved")]


@pytest.mark.acceptance(spec="009-channels", scenario="a denied approval is delivered to the agent")
async def test_deny_click_reaches_the_agent_and_non_owner_clicks_are_ignored(
    env: ChannelEnv,
) -> None:
    agent = ApprovalAgentAdapter()
    env.provider.adapter = agent
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "clean the build dir"))
    await wait_until(lambda: adapter.approval_prompts)
    prompt = adapter.approval_prompts[0]

    # A click from a chat that is not the paired owner decides nothing.
    await env.processor.on_approval_click(
        ApprovalClick(
            channel="tg",
            chat_id="stranger",
            value="req-1|deny",
            prompt_message_id=prompt.message_id,
        )
    )
    assert agent.decisions == []
    assert adapter.resolved == []

    # The owner's deny goes through.
    await env.processor.on_approval_click(
        ApprovalClick(
            channel="tg",
            chat_id="owner",
            value="req-1|deny",
            prompt_message_id=prompt.message_id,
        )
    )

    await wait_until(lambda: "decided:deny" in adapter.texts())
    assert agent.decisions == ["deny"]
    assert adapter.resolved == [("owner", prompt.message_id, "❌ Denied")]
