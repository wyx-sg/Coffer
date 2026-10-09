"""A thread turn folds a bounded slice of its thread, not the whole thread (spec
channels "Ground a thread turn in a bounded slice of the thread", "Say what a
thread read cannot show", "Download the media a thread's messages carry").

A conversation's first turn in a thread gets the thread's latest messages; each
later turn of the same conversation gets only what others posted since its
previous turn there. The per-conversation cursor lives in ``runs.db``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from coffer.application.channel.store_ports import ReplyRecord
from coffer.application.channel.turn_context import READ_THREAD_TOOL, THREAD_FOLD_LIMIT
from coffer.domain.channel.envelopes import InboundAttachment
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.domain.channel.thread_messages import ThreadMessage
from coffer.infrastructure.channel.persistence import ChannelReplyRepo, ChannelThreadCursorRepo

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, wait_until

_T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _message(n: int, sender: str = "alice@x.com", *, from_bot: bool = False) -> ThreadMessage:
    return ThreadMessage(
        message_id=f"m-{n}",
        sender=sender,
        sent_at=_T0 + timedelta(minutes=n),
        items=(ForwardedItem(sender=sender, text=f"message {n}"),),
        from_bot=from_bot,
    )


def _trigger(n: int) -> ThreadMessage:
    """The owner's own @mention, as the thread read returns it."""
    return _message(n, "owner@x.com")


async def _setup(env: ChannelEnv) -> tuple[Any, FakeChannelAdapter]:
    resource = await env.register_channel("st")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=True))
    await env.pair(resource, "owner", sender_id="owner-1")
    return resource, adapter


async def _mention(env: ChannelEnv, text: str, message_id: str) -> None:
    await env.processor.on_message(
        inbound(
            "st",
            "grp-1",
            text,
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="th-1",
            platform_message_id=message_id,
        )
    )


async def _turns(env: ChannelEnv, count: int) -> list[str]:
    """Every turn's text across the chat's conversations, oldest conversation
    first, once ``count`` turns have run."""
    for _ in range(500):
        conversations = await env.conversations()
        if sum(len(env.user_texts(c.id)) for c in conversations) >= count:
            break
        await asyncio.sleep(0.01)
    texts: list[str] = []
    for conversation in reversed(await env.conversations()):
        texts.extend(env.user_texts(conversation.id))
    return texts


@pytest.mark.acceptance(
    spec="channels",
    scenario="a conversation's first turn in a thread folds the thread's latest messages",
)
@pytest.mark.acceptance(
    spec="channels", scenario="a fold that leaves out older messages says how to read them"
)
async def test_the_first_turn_folds_the_latest_twenty_and_names_the_tool(env: ChannelEnv) -> None:
    _resource, adapter = await _setup(env)
    adapter.thread_messages = [_message(n) for n in range(25)] + [_trigger(25)]

    await _mention(env, "@bot sum it up", "m-25")
    [text] = await _turns(env, 1)

    assert text.startswith("[Thread messages]")
    assert "alice@x.com: message 5" in text
    assert "alice@x.com: message 24" in text
    assert "alice@x.com: message 4\n" not in text
    # The triggering message is the turn itself, not part of its context.
    assert "message 25" not in text
    shown = [line for line in text.splitlines() if line.startswith("alice@x.com:")]
    assert len(shown) == THREAD_FOLD_LIMIT
    note = next(line for line in text.splitlines() if line.startswith("note:"))
    assert "5 earlier messages in this thread are not shown" in note
    assert READ_THREAD_TOOL in note
    assert 'channel "st"' in note and 'thread_id "th-1"' in note and 'before "m-5"' in note
    assert text.endswith("@bot sum it up")


@pytest.mark.acceptance(
    spec="channels", scenario="a later turn folds only what was posted since the previous turn"
)
async def test_a_later_turn_folds_only_the_new_messages(env: ChannelEnv) -> None:
    _resource, adapter = await _setup(env)
    adapter.thread_messages = [_message(0), _message(1, "bob@x.com"), _trigger(2)]
    await _mention(env, "@bot first", "m-2")
    await _turns(env, 1)

    adapter.thread_messages = [
        _message(0),
        _message(1, "bob@x.com"),
        _trigger(2),
        _message(3, "", from_bot=True),  # the bot's own answer
        _message(4, "carol@x.com"),
        _message(5, "bob@x.com"),
        _trigger(6),
    ]
    await _mention(env, "@bot and now?", "m-6")
    first, second = await _turns(env, 2)

    assert "bob@x.com: message 1" in first
    assert second.startswith("[New thread messages since your last turn in this thread]")
    assert "carol@x.com: message 4" in second
    assert "bob@x.com: message 5" in second
    for already_seen in ("message 0", "message 1", "message 2", "message 3", "message 6"):
        assert already_seen not in second
    assert "note:" not in second


@pytest.mark.acceptance(
    spec="channels", scenario="a later turn with nothing new folds no thread context"
)
async def test_a_later_turn_with_nothing_new_folds_nothing(env: ChannelEnv) -> None:
    _resource, adapter = await _setup(env)
    adapter.thread_messages = [_message(0), _trigger(1)]
    await _mention(env, "@bot first", "m-1")
    await _turns(env, 1)

    adapter.thread_messages = [
        _message(0),
        _trigger(1),
        _message(2, "", from_bot=True),
        _trigger(3),
    ]
    await _mention(env, "@bot again", "m-3")
    _first, second = await _turns(env, 2)

    assert second == "@bot again"


async def test_a_reply_the_ledger_knows_is_the_bots_own(env: ChannelEnv) -> None:
    """A platform that does not flag the bot's messages still has them left out:
    the reply ledger names every message the bot sent."""
    _resource, adapter = await _setup(env)
    adapter.thread_messages = [_message(0), _trigger(1)]
    await _mention(env, "@bot first", "m-1")
    await _turns(env, 1)
    # A reply the bot sent, as the reply ledger records it.
    own = "r-2"
    await ChannelReplyRepo(env.cursors._sm).add(
        ReplyRecord(
            reply_id="reply-1",
            resource_uid=_resource.uid,
            chat_id="grp-1",
            thread_id="th-1",
            chat_kind="group",
            message_ids=(own,),
            sent_at=_T0,
        )
    )
    adapter.thread_messages = [
        _message(0),
        _trigger(1),
        ThreadMessage(
            message_id=own,
            sender="unknown",
            sent_at=_T0 + timedelta(minutes=2),
            items=(ForwardedItem(sender="unknown", text="Hello world"),),
        ),
        _trigger(3),
    ]
    await _mention(env, "@bot again", "m-3")
    _first, second = await _turns(env, 2)

    assert second == "@bot again"


@pytest.mark.acceptance(
    spec="channels", scenario="a new conversation in the thread is seeded again"
)
async def test_new_conversation_is_seeded_again(env: ChannelEnv) -> None:
    _resource, adapter = await _setup(env)
    adapter.thread_messages = [_message(0), _trigger(1)]
    await _mention(env, "@bot first", "m-1")
    await _turns(env, 1)

    await _mention(env, "/new", "m-2")
    await wait_until(lambda: len(adapter.texts()) >= 2)
    adapter.thread_messages = [_message(0), _trigger(1), _message(2), _trigger(3)]
    await _mention(env, "@bot fresh start", "m-3")
    texts = await _turns(env, 2)

    assert len(await env.conversations()) == 2
    assert texts[-1].startswith("[Thread messages]")
    assert "alice@x.com: message 0" in texts[-1]


@pytest.mark.acceptance(spec="channels", scenario="the thread cursor survives a daemon restart")
async def test_the_cursor_is_kept_in_the_database(env: ChannelEnv) -> None:
    resource, adapter = await _setup(env)
    adapter.thread_messages = [_message(0), _trigger(1)]
    await _mention(env, "@bot first", "m-1")
    await _turns(env, 1)
    [conversation] = await env.conversations()

    # A fresh repo over the same database file is what a restarted daemon reads.
    reopened = ChannelThreadCursorRepo(env.cursors._sm)
    cursor = await reopened.get(resource.uid, "grp-1", "th-1", conversation.id)
    assert cursor is not None
    assert cursor.last_message_id == "m-1"
    assert await reopened.list_for_thread(resource.uid, "grp-1", "th-1") == [cursor]


@pytest.mark.acceptance(spec="channels", scenario="only the folded messages' media is downloaded")
async def test_only_the_shown_messages_media_is_downloaded(env: ChannelEnv, tmp_path: Any) -> None:
    _resource, adapter = await _setup(env)
    image = tmp_path / "new.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    old = ThreadMessage(
        "m-0", "alice@x.com", _T0, (ForwardedItem("alice@x.com", "[image]"),), has_media=True
    )
    adapter.thread_messages = (
        [old]
        + [_message(n) for n in range(1, 21)]
        + [
            ThreadMessage(
                "m-21",
                "alice@x.com",
                _T0,
                (ForwardedItem("alice@x.com", "[image]"),),
                has_media=True,
            ),
            _trigger(22),
        ]
    )
    adapter.thread_media = {
        "m-21": (InboundAttachment(path=str(image), mime="image/png", filename="new.png"),)
    }

    await _mention(env, "@bot look", "m-22")
    await _turns(env, 1)

    assert adapter.media_downloads == ["m-21"]  # m-0 fell outside the slice


async def test_a_failed_read_leaves_the_cursor_where_it_was(env: ChannelEnv) -> None:
    resource, adapter = await _setup(env)
    adapter.thread_read_fails = True
    await _mention(env, "@bot hi", "m-1")
    [text] = await _turns(env, 1)

    assert text == "@bot hi"
    assert await env.cursors.list_for_thread(resource.uid, "grp-1", "th-1") == []


async def test_a_fresh_thread_marks_its_root_so_the_next_turn_folds_only_news(
    env: ChannelEnv,
) -> None:
    """A main-chat @mention roots a thread at itself: nothing is read, but the
    root is marked, so the next turn there does not seed the root back in."""
    _resource, adapter = await _setup(env)
    await env.processor.on_message(
        inbound(
            "st",
            "grp-1",
            "@bot hi",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="m-0",
            platform_message_id="m-0",
        )
    )
    await _turns(env, 1)
    assert adapter.fetch_thread_calls == []

    adapter.thread_messages = [_trigger(0), _message(1, "", from_bot=True), _trigger(2)]
    await env.processor.on_message(
        inbound(
            "st",
            "grp-1",
            "@bot more",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="m-0",
            platform_message_id="m-2",
        )
    )
    _first, second = await _turns(env, 2)
    assert second == "@bot more"
