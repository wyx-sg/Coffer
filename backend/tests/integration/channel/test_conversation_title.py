"""FR-048: a channel conversation is named after what the person typed.

Every turn's text opens with context blocks the channel folds in — the FR-042
origin block, and a thread's fetched history — which are the same on every turn
of every chat. Naming a conversation from that text gave the chat list a column
of identical `[Message origin] platform: …` titles. The channel passes the
human's own words down instead; the chat platform never learns the block format.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.domain.channel.envelopes import InboundAttachment
from coffer.domain.channel.rich_content import ForwardedItem

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, wait_until


async def _title(env: ChannelEnv) -> str:
    conversations = await env.chat.list_conversations()
    assert len(conversations) == 1
    return conversations[0].title


@pytest.mark.acceptance(
    spec="channels", scenario="a channel conversation is named by what the person typed"
)
async def test_a_channel_conversation_is_named_by_the_message_body(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(
        inbound("tg", "owner", "why did last night's ingestion job stall?")
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert await _title(env) == "why did last night's ingestion job stall?"


async def test_two_channel_conversations_are_told_apart(env: ChannelEnv) -> None:
    """The bug itself: two chats used to land under the same origin-block title."""
    resource, adapter = await env.paired_channel()
    await env.pair(resource, "owner-2")

    await env.processor.on_message(inbound("tg", "owner", "deploy status please"))
    await wait_until(lambda: len(adapter.texts()) == 1)
    await env.processor.on_message(inbound("tg", "owner-2", "who owns account-service?"))
    await wait_until(lambda: len(adapter.texts()) == 2)

    titles = {c.title for c in await env.chat.list_conversations()}
    assert titles == {"deploy status please", "who owns account-service?"}


async def test_thread_context_does_not_name_the_conversation(env: ChannelEnv) -> None:
    """A threaded message's prompt opens with the fetched history — the title
    still comes from the words this person just typed."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=True))
    await env.pair(resource, "owner", sender_id="owner-1")
    adapter.thread_items = [ForwardedItem(sender="Alice", text="the job is red again")]

    await env.processor.on_message(
        inbound("tg", "owner", "can you look at this?", thread_id="th-1", sender_id="owner-1")
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert await _title(env) == "can you look at this?"


async def test_an_image_only_message_is_named_by_its_filename(
    env: ChannelEnv, tmp_path: Path
) -> None:
    """No words at all: the filename is what a human recognises in the list —
    and it does not spend the title on wording every such message would share."""
    _resource, adapter = await env.paired_channel()
    image = tmp_path / "q3-latency.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")

    await env.processor.on_message(
        inbound(
            "tg",
            "owner",
            "",
            attachments=[
                InboundAttachment(path=str(image), mime="image/png", filename="q3-latency.png")
            ],
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert await _title(env) == "q3-latency.png"


async def test_a_name_the_owner_gave_outranks_the_message(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    conv = await env.chat.create_conversation(agent_key="builtin")
    await env.chat.rename_conversation(conv.id, new_title="Tax questions")
    await env.threads.set_active_conversation(resource.id, "owner", "", conv.id)

    await env.processor.on_message(inbound("tg", "owner", "and one more thing"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert await _title(env) == "Tax questions"
