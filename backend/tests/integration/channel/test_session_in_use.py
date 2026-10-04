"""A channel message for a session open in a terminal gets the refusal in the chat.

Spec chat "Run a session in one place at a time"; spec channels "Route the
owner's messages into a turn-platform conversation". The process list is a fake
port on the real orchestrator, renderer and fake channel adapter.
"""

from __future__ import annotations

import pytest

from coffer.domain.chat.agent_config import AgentConfig

from .conftest import ChannelEnv, inbound, wait_until

SID = "550e8400-e29b-41d4-a716-446655440000"
REFUSAL = "This session is open in a terminal — continue there, or send /thread to start a new one."


class _InUse:
    def __init__(self) -> None:
        self.busy = True

    async def in_use(self, session_id: str) -> bool:
        return self.busy and session_id == SID


async def _conversation_with_session(env: ChannelEnv, resource, adapter) -> str:
    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    await env.chat.set_agent_config(conversation_id, AgentConfig(session_id=SID))
    return conversation_id


@pytest.mark.acceptance(
    spec="chat", scenario="a session open in a terminal refuses the channel turn"
)
async def test_the_chat_is_told_exactly_and_no_turn_starts(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    await _conversation_with_session(env, resource, adapter)
    port = _InUse()
    env.orchestrator._session_in_use = port
    before = len(env.provider.adapter.recorded_prompts)

    await env.processor.on_message(inbound("tg", "owner", "are you there?"))

    await wait_until(lambda: any(REFUSAL in t for t in adapter.texts()))
    assert REFUSAL in adapter.texts()
    assert not any("⚠️" in t or "Send it again" in t for t in adapter.texts())
    assert len(env.provider.adapter.recorded_prompts) == before


@pytest.mark.acceptance(spec="chat", scenario="a session whose terminal closed runs again")
async def test_the_next_message_runs_once_the_terminal_has_closed(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    await _conversation_with_session(env, resource, adapter)
    port = _InUse()
    env.orchestrator._session_in_use = port
    await env.processor.on_message(inbound("tg", "owner", "one"))
    await wait_until(lambda: any(REFUSAL in t for t in adapter.texts()))
    before = len(env.provider.adapter.recorded_prompts)

    port.busy = False
    await env.processor.on_message(inbound("tg", "owner", "two"))

    await wait_until(lambda: len(env.provider.adapter.recorded_prompts) == before + 1)
