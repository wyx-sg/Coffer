"""A burst of channel messages drives one turn (spec channels "Take a burst of
messages as one turn"), end to end through the real inbound pipeline."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from coffer.application.channel import inbound_burst

from .conftest import (
    ChannelEnv,
    FakeChannelAdapter,
    inbound,
    tap_event,
    uid_of,
    wait_until,
)


@pytest.fixture
def short_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inbound_burst, "MAX_WINDOW_SECONDS", 60.0)


def _with_windows(env: ChannelEnv, *, text: float, forward: float) -> None:
    """Rebind the paired channel with its own quiet windows, as its config would."""
    binding = env.processor.binding(uid_of("tg"))
    assert binding is not None
    env.processor.bind(
        dataclasses.replace(
            binding, wait_after_text_seconds=text, wait_after_forward_seconds=forward
        )
    )


async def _user_turns(env: ChannelEnv, conversation_id: str) -> list[str]:
    return env.user_texts(conversation_id)


@pytest.mark.acceptance(
    spec="channels", scenario="a forwarded record and its follow-up become one turn"
)
async def test_a_forwarded_record_and_its_follow_up_run_as_one_turn(
    short_windows: None, env: ChannelEnv
) -> None:
    resource, adapter = await env.paired_channel()
    _with_windows(env, text=0.05, forward=2.0)
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


@pytest.mark.acceptance(
    spec="channels", scenario="messages further apart than the window are separate turns"
)
async def test_messages_further_apart_than_the_window_run_as_separate_turns(
    short_windows: None, env: ChannelEnv
) -> None:
    resource, _adapter = await env.paired_channel()
    _with_windows(env, text=0.03, forward=0.03)
    await env.send(inbound("tg", "owner", "one", platform_message_id="pm-1"))
    await asyncio.sleep(0.06)  # past the quiet window: the first is its own turn
    await env.send(inbound("tg", "owner", "two", platform_message_id="pm-2"))
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    await wait_until(lambda: env.orchestrator.pending(conversation_id) == [])
    assert await _user_turns(env, conversation_id) == ["one", "two"]


@pytest.mark.acceptance(spec="channels", scenario="/stop drops messages still being held")
async def test_stop_drops_the_held_burst_and_marks_each_message_stopped(
    short_windows: None, env: ChannelEnv
) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_reactions=True))
    await env.pair(resource, "owner")
    _with_windows(env, text=5.0, forward=5.0)

    await env.processor.on_message(inbound("tg", "owner", "first", platform_message_id="pm-1"))
    await env.processor.on_message(inbound("tg", "owner", "second", platform_message_id="pm-2"))
    await env.processor.on_message(inbound("tg", "owner", "/stop"))

    assert await env.active_conversation(resource) is None  # no turn ever started
    # Both had been acknowledged on arrival; the stop leaves neither on 👀.
    assert ("owner", "pm-1", "🤷") in adapter.reactions
    assert ("owner", "pm-2", "🤷") in adapter.reactions


@pytest.mark.acceptance(
    spec="channels", scenario="a forwarded record and its follow-up become one turn"
)
async def test_every_message_of_a_burst_carries_the_turns_marks(
    short_windows: None, env: ChannelEnv
) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_reactions=True))
    await env.pair(resource, "owner")
    _with_windows(env, text=0.05, forward=0.05)

    await env.processor.on_message(inbound("tg", "owner", "one", platform_message_id="pm-1"))
    await env.processor.on_message(inbound("tg", "owner", "two", platform_message_id="pm-2"))
    await wait_until(
        lambda: {("owner", "pm-1", "👌"), ("owner", "pm-2", "👌")} <= set(adapter.reactions),
        message="a message of the burst never got the done mark",
    )

    # One turn answered both, so both go received -> working -> done.
    for message_id in ("pm-1", "pm-2"):
        assert [e for _c, m, e in adapter.reactions if m == message_id] == ["👀", "👨‍💻", "👌"]


async def test_tapping_a_command_button_releases_the_held_burst_first(
    short_windows: None, env: ChannelEnv
) -> None:
    resource, _adapter = await env.paired_channel()
    _with_windows(env, text=5.0, forward=5.0)
    await env.processor.on_message(inbound("tg", "owner", "held"))

    await env.processor.on_callback(tap_event("tg", "owner", "cmd:status"))

    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None  # the held message was released, not left behind
    await wait_until(lambda: env.orchestrator.pending(conversation_id) == [])
    assert await _user_turns(env, conversation_id) == ["held"]


async def test_tapping_stop_drops_the_held_burst(short_windows: None, env: ChannelEnv) -> None:
    resource, _adapter = await env.paired_channel()
    _with_windows(env, text=5.0, forward=5.0)
    await env.processor.on_message(inbound("tg", "owner", "held"))

    await env.processor.on_callback(tap_event("tg", "owner", "cmd:stop"))

    assert env.processor._burst.holding(("tg", "owner", "")) is False
    assert await env.active_conversation(resource) is None  # it never became a turn
