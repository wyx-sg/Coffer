"""A quoted message grounds the turn ("Ground a turn in the message it quotes").

The transport resolves the quoted body with its own credentials and the core
folds it in as ``> sender: …`` lines right above the message — so "repeat this"
or "as above" points at something the agent can read.
"""

from __future__ import annotations

import pytest

from coffer.domain.channel.rich_content import ForwardedItem
from coffer.domain.chat.message import Role, TextBlock

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, turn_body, wait_until


async def _user_turn(env: ChannelEnv) -> str:
    conversations = await env.chat.list_conversations()
    messages = await env.chat.list_messages(conversations[0].id)
    (user,) = [m for m in messages if m.role == Role.USER]
    return "".join(b.text for b in user.content if isinstance(b, TextBlock))


@pytest.mark.acceptance(spec="channels", scenario="a quoted message is folded into the turn")
async def test_a_main_chat_mention_quoting_a_message_carries_its_body(env: ChannelEnv) -> None:
    # The screenshot case: bot pulled into a group, owner quotes an earlier message
    # in the MAIN chat and @mentions the bot. The @mention roots a fresh thread at
    # itself, so there is no thread to read — the quote is the only context.
    resource = await env.register_channel("st")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=True))
    await env.pair(resource, "owner", sender_id="owner-1")
    adapter.quoted_items = [ForwardedItem(sender="alice@example.com", text="讲个笑话")]

    await env.processor.on_message(
        inbound(
            "st",
            "grp-1",
            "@bot repeat this msg",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            platform_message_id="pm-9",
            thread_id="pm-9",
            quoted_message_id="mq-1",
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert adapter.fetch_quoted_calls == ["mq-1"]
    assert adapter.fetch_thread_calls == []
    turn = await _user_turn(env)
    assert "quoted message: mq-1" in turn  # the origin block still names it
    assert turn_body(turn) == "> alice@example.com: 讲个笑话\n@bot repeat this msg"


async def test_a_quote_inside_a_thread_sits_between_the_thread_and_the_message(
    env: ChannelEnv,
) -> None:
    resource = await env.register_channel("st")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=True))
    await env.pair(resource, "owner", sender_id="owner-1")
    adapter.thread_items = [ForwardedItem(sender="bob@example.com", text="status?")]
    adapter.quoted_items = [ForwardedItem(sender="alice@example.com", text="[image] x")]

    await env.processor.on_message(
        inbound(
            "st",
            "grp-1",
            "@bot what is this",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="th-1",
            quoted_message_id="mq-2",
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert turn_body(await _user_turn(env)) == (
        "[Thread messages]\nbob@example.com: status?\n\n"
        "> alice@example.com: [image] x\n@bot what is this"
    )


async def test_a_transport_without_history_fetch_is_never_asked(env: ChannelEnv) -> None:
    # Telegram inlines the quote on the update itself; the core must not ask.
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=False))
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(
        inbound("tg", "owner", "hi", sender_id="owner-1", quoted_message_id="mq-3")
    )
    await wait_until(lambda: "Hello world" in adapter.texts())
    assert adapter.fetch_quoted_calls == []
