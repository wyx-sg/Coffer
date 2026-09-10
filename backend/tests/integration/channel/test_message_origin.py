"""FR-042: every channel turn carries its own origin.

The agent used to see only the message text, so "which group am I in?" was a
guess it could only answer by listing the bot's groups and inferring. The turn
text now opens with an origin block naming the platform, the chat (kind, title
where the platform gives one, and always the chat id), the thread, and the
sender — on every turn, so an agent switch or a resumed session never loses it.
"""

from __future__ import annotations

import pytest

from coffer.domain.chat.message import Role, TextBlock

from .conftest import ChannelEnv, inbound, wait_until


def _text(message: object) -> str:  # type: ignore[no-untyped-def]
    return "".join(b.text for b in message.content if isinstance(b, TextBlock))  # type: ignore[attr-defined]


async def _user_texts(env: ChannelEnv) -> list[str]:
    conversations = await env.chat.list_conversations()
    messages = await env.chat.list_messages(conversations[0].id)
    return [_text(m) for m in messages if m.role is Role.USER]


@pytest.mark.acceptance(spec="channels", scenario="a group turn names the group it came from")
async def test_group_turn_carries_the_chat_id_title_thread_and_sender(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel(sender_id="owner-1")

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
        'chat: group "account-campaign-reaction" (id: grp-1)\n'
        "thread: th-1\n"
        "from: yuxing.wu@shopee.com (id: owner-1)\n"
        "\n"
        "@bot which group is this?"
    )


@pytest.mark.acceptance(spec="channels", scenario="a DM turn names its own chat")
async def test_dm_turn_carries_a_direct_origin_block(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert (await _user_texts(env))[0] == (
        "[Message origin]\nplatform: telegram\nchat: direct (id: owner)\nfrom: Owner\n\nhi"
    )


@pytest.mark.acceptance(spec="channels", scenario="every turn carries its origin")
async def test_origin_is_repeated_on_later_turns_not_just_the_first(env: ChannelEnv) -> None:
    """An agent can be switched mid-conversation (``/agent``) and a session can
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

    assert any("/agent" in text for _chat, text in adapter.sent)
    assert not any("[Message origin]" in text for _chat, text in adapter.sent)
    assert await env.chat.list_conversations() == []
