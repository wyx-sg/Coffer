"""Only the reserved words are commands; every other slash text is a message
(spec channels "Pass unreserved slash text to the agent")."""

from __future__ import annotations

import pytest

from .conftest import ChannelEnv, inbound, wait_until


async def _turn_texts(env: ChannelEnv) -> list[str]:
    [conversation] = await env.conversations()
    return env.user_texts(conversation.id)


@pytest.mark.acceptance(spec="channels", scenario="an unreserved slash word reaches the agent")
async def test_an_unreserved_slash_word_reaches_the_agent(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.send(inbound("tg", "owner", "/compact keep the decisions"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert await _turn_texts(env) == ["/compact keep the decisions"]


@pytest.mark.acceptance(
    spec="channels", scenario="a message starting with a path reaches the agent"
)
async def test_a_message_starting_with_a_path_reaches_the_agent(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.send(inbound("tg", "owner", "/Users/me/app crashes on start"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert await _turn_texts(env) == ["/Users/me/app crashes on start"]


@pytest.mark.acceptance(spec="channels", scenario="a near miss of a command is corrected, not sent")
async def test_a_near_miss_is_corrected_not_sent(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.send(inbound("tg", "owner", "/stpo"))
    await env.send(inbound("tg", "owner", "/threads"))

    assert adapter.texts() == [
        "Unknown command /stpo. Did you mean /stop? Send /help for all commands.",
        "Unknown command /threads. Did you mean /thread? Send /help for all commands.",
    ]
    assert await env.conversations() == []


@pytest.mark.acceptance(spec="channels", scenario="a removed command reaches the agent as text")
async def test_a_removed_command_reaches_the_agent_as_text(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.send(inbound("tg", "owner", "/agent codex"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert await _turn_texts(env) == ["/agent codex"]
    assert not any("Unknown command" in t for t in adapter.texts())


async def test_a_command_is_matched_whatever_its_case(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.send(inbound("tg", "owner", "/Model high"))

    assert adapter.texts() == ["Model: high — from your next message"]


async def test_a_did_you_mean_in_a_group_is_private(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel(sender_id="4242")

    await env.send(
        inbound("tg", "-100g", "/stauts", chat_kind="group", sender_id="4242", ephemeral_id="77")
    )

    assert adapter.texts() == [
        "Unknown command /stauts. Did you mean /status? Send /help for all commands."
    ]
    target = adapter.sent_ephemeral[-1]
    assert target is not None and target.receiver_id == "4242"
