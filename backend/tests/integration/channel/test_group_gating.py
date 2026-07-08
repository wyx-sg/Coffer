"""Task 7b: group owner gating, non-owner refusal, and thread-context assembly.

Task 7a already added per-(channel, chat_id, thread_id) sessions and
thread-scoped replies (see ``test_thread_sessions.py``); this covers what sits
in front of that plumbing for a group chat: un-addressed messages are ignored,
a non-owner @mention is refused, an owner @mention drives a turn and records a
peer row for the group/thread, and — when the transport can fetch thread
history — the thread's own messages are folded into the turn text.
"""

from __future__ import annotations

import pytest

from coffer.domain.channel.rich_content import ForwardedItem
from coffer.domain.chat.message import Role, TextBlock

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, wait_until


def _text(message: object) -> str:  # type: ignore[no-untyped-def]
    return "".join(b.text for b in message.content if isinstance(b, TextBlock))  # type: ignore[attr-defined]


@pytest.mark.acceptance(spec="009-channels", scenario="an un-addressed group message is ignored")
async def test_unaddressed_group_message_is_ignored(env: ChannelEnv) -> None:
    """A group message with no @mention/reply-to-bot never drives a turn and
    never even creates a peer row for the group chat."""
    resource, adapter = await env.paired_channel(sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "just chatting amongst ourselves",
            chat_kind="group",
            addressed=False,
            sender_id="owner-1",
        )
    )

    assert adapter.sent == []
    assert await env.chat.list_conversations() == []
    assert await env.peers.get_by_chat(resource.id, "grp-1") is None


@pytest.mark.acceptance(
    spec="009-channels", scenario="an empty sender_id in a group cannot bypass the owner gate"
)
async def test_empty_sender_id_in_a_group_is_refused_not_treated_as_owner(
    env: ChannelEnv,
) -> None:
    """Regression: a group message with no resolvable ``sender_id`` (the
    transport could not supply one) must be refused like any other
    non-owner, never silently treated as the owner. A group chat is shared,
    so falling through here would let an unidentifiable member drive turns
    on the owner's agent."""
    resource, adapter = await env.paired_channel(sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "@bot help me",
            chat_kind="group",
            addressed=True,
            sender_id="",
            thread_id="th-1",
        )
    )

    assert len(adapter.sent) == 1
    chat_id, text = adapter.sent[0]
    assert chat_id == "grp-1"
    assert "Not authorized" in text
    assert adapter.sent_routed[0] == (chat_id, text, "th-1", "group")
    # No turn was started and no peer row was created for the unverified sender.
    assert await env.chat.list_conversations() == []
    assert await env.peers.get_by_chat(resource.id, "grp-1") is None


@pytest.mark.acceptance(spec="009-channels", scenario="a non-owner @mention in a group is refused")
async def test_non_owner_mention_in_a_group_is_refused(env: ChannelEnv) -> None:
    """An @mention from someone other than the channel's paired owner gets a
    refusal reply routed to the group chat/thread — no turn is driven."""
    resource, adapter = await env.paired_channel(sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "@bot help me",
            chat_kind="group",
            addressed=True,
            sender_id="intruder-1",
            thread_id="th-1",
        )
    )

    assert len(adapter.sent) == 1
    chat_id, text = adapter.sent[0]
    assert chat_id == "grp-1"
    assert "Not authorized" in text
    assert adapter.sent_routed[0] == (chat_id, text, "th-1", "group")
    assert await env.chat.list_conversations() == []
    # No peer row was created for the intruder's turn attempt.
    assert await env.peers.get_by_chat(resource.id, "grp-1") is None


@pytest.mark.acceptance(
    spec="009-channels", scenario="the owner @mentions the bot in a group main chat"
)
async def test_owner_mention_in_group_main_drives_a_turn_and_creates_a_peer(
    env: ChannelEnv,
) -> None:
    """The owner @mentioning the bot in a group's main chat drives a turn and,
    since no peer row existed yet for this chat, creates one. The adapter roots
    a fresh thread at the @mention (``thread_id`` == the @mention's
    ``platform_message_id``), so the reply routes back into that thread, never
    the group main chat."""
    resource, adapter = await env.paired_channel(sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "@bot hi there",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="pm-1",  # what the adapter synthesises for a main-chat @mention
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    match = next(r for r in adapter.sent_routed if r[1] == "Hello world")
    _chat_id, _reply_text, thread_id, chat_kind = match
    assert thread_id == "pm-1"
    assert chat_kind == "group"

    peer = await env.peers.get_by_chat(resource.id, "grp-1")
    assert peer is not None
    assert peer.sender_id == "owner-1"


@pytest.mark.acceptance(spec="009-channels", scenario="the owner @mentions the bot inside a thread")
async def test_owner_mention_in_a_thread_folds_fetched_history_into_the_turn(
    env: ChannelEnv,
) -> None:
    """When the transport supports history fetch and the @mention landed in a
    thread, the thread's own messages are prepended to the turn text and the
    reply is routed back into that same thread."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=True))
    await env.pair(resource, "owner", sender_id="owner-1")
    adapter.thread_items = [
        ForwardedItem(sender="Alice", text="what's the status?"),
        ForwardedItem(sender="Bob", text="waiting on the deploy"),
    ]

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "@bot summarize this thread",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="th-1",
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert adapter.fetch_thread_calls == [("grp-1", "th-1")]
    match = next(r for r in adapter.sent_routed if r[1] == "Hello world")
    _chat_id, _reply_text, thread_id, chat_kind = match
    assert thread_id == "th-1"
    assert chat_kind == "group"

    conversations = await env.chat.list_conversations()
    assert len(conversations) == 1
    messages = await env.chat.list_messages(conversations[0].id)
    user_messages = [m for m in messages if m.role == Role.USER]
    assert len(user_messages) == 1
    user_text = _text(user_messages[0])
    assert user_text.startswith("[Thread messages]")
    assert "Alice: what's the status?" in user_text
    assert "Bob: waiting on the deploy" in user_text
    assert user_text.endswith("@bot summarize this thread")


async def test_group_main_mention_roots_a_thread_and_skips_self_fetch(
    env: ChannelEnv,
) -> None:
    """A group-main @mention arrives already threaded under its own message —
    the adapter roots a fresh thread there, so ``thread_id`` equals the
    @mention's ``platform_message_id``. That thread holds only the @mention
    itself, so no history is fetched (fetching would just echo the @mention
    back into its own context); the turn runs on the @mention text alone and
    the reply is routed into that thread, never the group main chat."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=True))
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "@bot hi",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="pm-1",  # == the inbound helper's platform_message_id
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert adapter.fetch_thread_calls == []  # nothing else in the thread yet
    match = next(r for r in adapter.sent_routed if r[1] == "Hello world")
    _chat_id, _reply_text, thread_id, chat_kind = match
    assert thread_id == "pm-1"
    assert chat_kind == "group"


async def test_owner_mention_in_a_thread_skips_fetch_when_unsupported(env: ChannelEnv) -> None:
    """A transport that cannot fetch thread history (Telegram's Bot API) is
    never asked to — the turn runs on the @mention text alone."""
    _resource, adapter = await env.paired_channel(sender_id="owner-1")
    assert adapter.capabilities.supports_history_fetch is False

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "@bot what's up",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="th-1",
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert adapter.fetch_thread_calls == []
    conversations = await env.chat.list_conversations()
    assert len(conversations) == 1
    messages = await env.chat.list_messages(conversations[0].id)
    user_messages = [m for m in messages if m.role == Role.USER]
    assert len(user_messages) == 1
    assert _text(user_messages[0]) == "@bot what's up"


async def test_dm_still_pairs_and_drives_a_turn(env: ChannelEnv) -> None:
    """DM regression: a plain unpaired DM still bootstraps pairing via the
    pairing code, and a paired DM still drives a turn as before, now resolved
    through ``get_by_chat`` instead of the legacy single-peer accessor."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)
    code, _expires = env.pairing.issue("tg")

    await env.processor.on_message(inbound("tg", "owner", code, sender_display="Owner"))
    peer = await env.peers.get_by_chat(resource.id, "owner")
    assert peer is not None
    assert adapter.sent[0][1].startswith("✅ Paired.")

    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    assert ("owner", "Hello world") in adapter.sent
