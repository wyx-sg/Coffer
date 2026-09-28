"""A burst of channel messages drives one turn (spec channels "Take a burst of
messages as one turn"), end to end through the real inbound pipeline."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from coffer.application.channel import inbound_burst
from coffer.domain.chat.message import Role, TextBlock

from .conftest import ChannelEnv, inbound, turn_body, wait_until


@pytest.fixture
def short_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inbound_burst, "MAX_WINDOW_SECONDS", 60.0)


def _with_windows(env: ChannelEnv, *, text: float, forward: float) -> None:
    """Rebind the paired channel with its own quiet windows, as its config would."""
    binding = env.processor.binding("tg")
    assert binding is not None
    env.processor.bind(
        dataclasses.replace(
            binding, wait_after_text_seconds=text, wait_after_forward_seconds=forward
        )
    )


async def _user_turns(env: ChannelEnv, conversation_id: str) -> list[str]:
    messages = await env.chat.list_messages(conversation_id)
    return [
        turn_body("".join(b.text for b in m.content if isinstance(b, TextBlock)))
        for m in messages
        if m.role == Role.USER
    ]


async def test_a_forwarded_record_and_its_follow_up_run_as_one_turn(
    short_windows: None, env: ChannelEnv
) -> None:
    resource, adapter = await env.paired_channel()
    _with_windows(env, text=0.05, forward=0.4)
    record = dataclasses.replace(
        inbound("tg", "owner", "Forwarded chat record\nalice: the build is red"),
        forwarded=True,
        platform_message_id="pm-1",
    )
    await env.processor.on_message(record)
    # Past the short window but inside the long one a forwarded record earns.
    await asyncio.sleep(0.15)
    await env.processor.on_message(
        inbound("tg", "owner", "look into this", platform_message_id="pm-2")
    )
    # Both were acknowledged on arrival, before any turn ran.
    assert adapter.typing[:2] == ["owner", "owner"]

    await wait_until(lambda: env.processor._burst.holding(("tg", "owner", "")) is False)
    await env.processor._burst.settled()
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    await wait_until(lambda: env.orchestrator.pending(conversation_id) == [])
    turns = await _user_turns(env, conversation_id)
    assert turns == ["Forwarded chat record\nalice: the build is red\n\nlook into this"]


async def test_a_command_releases_the_held_burst_first(
    short_windows: None, env: ChannelEnv
) -> None:
    resource, _adapter = await env.paired_channel()
    _with_windows(env, text=0.05, forward=0.4)
    await env.processor.on_message(inbound("tg", "owner", "held"))
    await env.processor.on_message(inbound("tg", "owner", "/status"))
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    # The held message reached the conversation before /status answered.
    await wait_until(lambda: env.orchestrator.pending(conversation_id) == [])
    assert await _user_turns(env, conversation_id) == ["held"]
