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

from coffer.application.channel.conversation_ops import ensure_conversation
from coffer.application.channel.ports import ChannelPeer

from .conftest import ChannelEnv, inbound, wait_until


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
