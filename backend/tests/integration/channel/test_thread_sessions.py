"""Task 7a: per-(channel, chat_id, thread_id) sessions and thread-scoped
replies — pure plumbing, no group gating or context fetching (that's 7b).

DM behavior must stay byte-for-byte identical: a threadless DM still drives a
turn and replies with ``chat_kind="direct"``/``thread_id=""``. What's new is
that a message carrying a non-empty ``thread_id`` gets its reply routed back
into that same thread, and that two threads sharing a chat_id drain
independently (their own queue, their own draining turn).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.channel.conversation_ops import ensure_conversation
from coffer.application.channel.ports import ChannelPeer
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.domain.chat.message import Role, TextBlock

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, turn_body, wait_until


async def test_dm_reply_defaults_to_direct_chat_kind_and_empty_thread(env: ChannelEnv) -> None:
    """DM regression: a plain DM still drives a turn and its reply is routed
    with the untouched defaults (``chat_kind="direct"``, ``thread_id=""``)."""
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    match = next(r for r in adapter.sent_routed if r[1] == "Hello world")
    _chat_id, _text, thread_id, chat_kind = match
    assert thread_id == ""
    assert chat_kind == "direct"


async def test_dm_message_in_a_thread_replies_in_the_same_thread(env: ChannelEnv) -> None:
    """A DM message carrying a ``thread_id`` gets its reply routed back into
    that thread — the reply's ``send_text`` call carries the same thread_id."""
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi", thread_id="t9"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    match = next(r for r in adapter.sent_routed if r[1] == "Hello world")
    _chat_id, _text, thread_id, _chat_kind = match
    assert thread_id == "t9"


async def test_same_chat_different_threads_get_separate_sessions(env: ChannelEnv) -> None:
    """Two messages with the same chat_id but different thread_id are keyed
    to two different ``_Session`` objects — each thread drains on its own."""
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi", thread_id="t1"))
    await wait_until(lambda: len(adapter.texts()) >= 1)
    await env.processor.on_message(inbound("tg", "owner", "hi again", thread_id="t2"))
    await wait_until(lambda: len(adapter.texts()) >= 2)

    keys = [key for key in env.processor._sessions if key[0] == "tg" and key[1] == "owner"]
    assert len(keys) == 2
    assert {key[2] for key in keys} == {"t1", "t2"}


async def test_ensure_conversation_sets_active_conversation_on_the_matching_thread_row(
    env: ChannelEnv,
) -> None:
    """``ensure_conversation`` binds the conversation to the per-thread row
    keyed ``(resource_id, chat_id, thread_id)`` (FR-032): opening one thread's
    conversation must not disturb another chat's/thread's."""
    resource = await env.register_channel("tg")
    env.bind(resource)
    group = ChannelPeer(
        resource_id=resource.id,
        chat_id="group-1",
        display_name="Group",
        paired_at=datetime.now(tz=UTC),
        active_conversation_id=None,
    )
    await env.peers.upsert(group)

    binding = env.processor.binding("tg")
    assert binding is not None
    conversation_id = await ensure_conversation(env.chat, env.threads, binding, group, "")

    bound = await env.threads.get(resource.id, "group-1", "")
    assert bound is not None
    assert bound.active_conversation_id == conversation_id

    # A different chat's DM thread has no binding conjured for it.
    assert await env.threads.get(resource.id, "dm-1", "") is None


# ---------------------------------------------------------------------------
# Thread context is no longer a group-only affair (SeaTalk's DM thread endpoint)
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels", scenario="a DM thread grounds its turn in the thread's own messages"
)
async def test_dm_message_inside_a_thread_fetches_that_thread_s_context(
    env: ChannelEnv,
) -> None:
    """A DM thread grounds its turn exactly like a group thread does — the
    adapter is told which kind it is so it reads the direct-chat thread
    endpoint (``single_chat/get_thread_by_thread_id``), not the group one."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=True))
    await env.pair(resource, "owner", sender_id="owner-1")
    adapter.thread_items = [ForwardedItem(sender="Owner", text="what did we decide?")]

    await env.processor.on_message(
        inbound("tg", "owner", "remind me", sender_id="owner-1", thread_id="th-1")
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert adapter.fetch_thread_calls == [("owner", "th-1")]
    assert adapter.fetch_thread_kinds == ["direct"]
    conversations = await env.chat.list_conversations()
    messages = await env.chat.list_messages(conversations[0].id)
    user_text = turn_body(
        "".join(
            b.text
            for m in messages
            if m.role == Role.USER
            for b in m.content
            if isinstance(b, TextBlock)
        )
    )
    assert "Owner: what did we decide?" in user_text
    assert user_text.endswith("remind me")


async def test_threadless_dm_fetches_no_context(env: ChannelEnv) -> None:
    """A DM that is not in a thread has no thread to read — the main DM history
    is never fetched (only the thread a message actually landed in is)."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=True))
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(inbound("tg", "owner", "hi", sender_id="owner-1"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert adapter.fetch_thread_calls == []


async def test_dm_message_rooting_its_own_thread_skips_the_fetch(env: ChannelEnv) -> None:
    """A message whose thread is rooted at itself holds nothing else yet —
    fetching would only echo it back into its own context."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=True))
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(
        # ``inbound`` stamps platform_message_id="pm-1"
        inbound("tg", "owner", "hi", sender_id="owner-1", thread_id="pm-1")
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert adapter.fetch_thread_calls == []
