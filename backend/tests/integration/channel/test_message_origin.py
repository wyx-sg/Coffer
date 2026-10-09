"""Every channel turn carries its own origin ("Open every turn with its message origin").

The agent used to see only the message text, so "which group am I in?" was a
guess it could only answer by listing the bot's groups and inferring. The turn
text now opens with an origin block naming the platform, the chat (kind, title
where the platform gives one, and always the chat id), the thread, and the
sender — on every turn, so an agent switch or a resumed session never loses it.
"""

from __future__ import annotations

import pytest

from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.thread_tool import ThreadReader

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, wait_until


async def _user_texts(env: ChannelEnv) -> list[str]:
    conversations = await env.conversations()
    return env.raw_prompts(conversations[0].id)


@pytest.mark.acceptance(spec="channels", scenario="a group turn names the group it came from")
async def test_group_turn_carries_the_chat_id_title_thread_and_sender(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel(sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "@bot which group is this?",
            chat_kind="group",
            chat_title="account-campaign-reaction",
            addressed=True,
            sender_id="owner-1",
            sender_display="yuxing.wu@shopee.com",
            thread_id="th-1",
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert (await _user_texts(env))[0] == (
        "[Message origin]\n"
        "platform: telegram\n"
        f'channel: "tg" (id: {resource.uid})\n'
        'chat: group "account-campaign-reaction" (id: grp-1)\n'
        "thread: th-1\n"
        "from: yuxing.wu@shopee.com (id: owner-1)\n"
        "\n"
        "@bot which group is this?"
    )


@pytest.mark.acceptance(spec="channels", scenario="a DM turn names its own chat")
async def test_dm_turn_carries_a_direct_origin_block(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert (await _user_texts(env))[0] == (
        f'[Message origin]\nplatform: telegram\nchannel: "tg" (id: {resource.uid})\n'
        "chat: direct (id: owner)\nfrom: Owner (id: owner)\n\nhi"
    )


@pytest.mark.acceptance(spec="channels", scenario="every turn carries its origin")
async def test_origin_is_repeated_on_later_turns_not_just_the_first(env: ChannelEnv) -> None:
    """An agent can be switched between conversations (``/new <agent>``) and a session can
    be resumed, so a first-turn-only header would silently go missing."""
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "first"))
    await wait_until(lambda: len(adapter.texts()) == 1)
    await env.processor.on_message(inbound("tg", "owner", "second"))
    await wait_until(lambda: len(adapter.texts()) == 2)

    texts = await _user_texts(env)
    assert len(texts) == 2
    assert all(t.startswith("[Message origin]") for t in texts)
    assert texts[0].endswith("\n\nfirst") and texts[1].endswith("\n\nsecond")


@pytest.mark.acceptance(spec="channels", scenario="a slash command keeps its leading slash")
async def test_a_command_is_not_prefixed_with_an_origin_block(env: ChannelEnv) -> None:
    """The origin block is folded in after command detection — prefixing it
    first would turn every ``/command`` into an ordinary turn."""
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/help"))

    assert any("/model" in text for _chat, text in adapter.sent)
    assert not any("[Message origin]" in text for _chat, text in adapter.sent)
    assert await env.conversations() == []


@pytest.mark.acceptance(
    spec="channels", scenario="the origin block carries the channel's id and the tool takes it"
)
async def test_the_origin_block_carries_the_channel_id_and_the_tool_takes_it(
    env: ChannelEnv,
) -> None:
    resource = await env.register_channel("Team bot!")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=True))
    await env.pair(resource, "owner", sender_id="owner-1")
    await env.pair(resource, "grp-1", sender_id="owner-1")

    await env.processor.on_message(inbound("Team bot!", "owner", "hi", sender_id="owner-1"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    assert f'channel: "Team bot!" (id: {resource.uid})\n' in (await _user_texts(env))[0]

    async def running_channel(ref: str) -> ChannelBinding | None:
        # The resolution the daemon wires: a uid or a name.
        for channel in await env.resources.list(kind="channel"):
            if ref in (channel.uid, channel.name):
                return env.processor.binding(channel.uid)
        return None

    reader = ThreadReader(resolve=running_channel, peers=env.peers)
    args = {"chat_id": "grp-1", "chat_kind": "group", "thread_id": "th-1"}
    by_id = await reader.read({"channel": resource.uid, **args})
    by_name = await reader.read({"channel": "Team bot!", **args})
    assert by_id == by_name
    assert adapter.fetch_thread_calls  # the call reached that channel's adapter

    # A rename never breaks a call that names the id.
    await env.resources.rename(resource.uid, "Office bot", actor="test")
    assert await reader.read({"channel": resource.uid, **args}) == by_id
