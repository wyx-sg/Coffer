"""TelegramAdapter against an in-process fake Bot API (no real network).

Covers the long-poll loop (dispatch, offset-after-dispatch, error backoff),
outbound rendering (HTML with plain-text retry, chunking), and the Bot API
method mapping for edit/delete/typing/approval prompts.
"""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from coffer.domain.channel.envelopes import ChoiceButton, EphemeralTarget
from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel.live_text import TelegramLiveText
from coffer.infrastructure.channel.telegram import TelegramAdapter
from coffer.infrastructure.channel.telegram_draft import TelegramDraftLiveText
from coffer.infrastructure.channel.telegram_profile import BotIdentity

from .conftest import (
    FakeSeaTalk,
    FakeTelegram,
    RecordingCallbacks,
    make_seatalk_adapter,
    make_telegram_adapter,
    wait_until,
)


def _live_ticking(step: float = 2.0):  # type: ignore[no-untyped-def]
    """A clock that advances past the live surface's buffer on every read, so a
    test drives updates deterministically instead of sleeping.

    The step must clear the LARGEST buffer any surface uses — Telegram's is
    1.5 s, because it edits a real message and its flood limits are tighter than
    a streaming endpoint's.
    """
    box = [0.0]

    def now() -> float:
        value = box[0]
        box[0] += step
        return value

    return now


def _message_update(update_id: int, *, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1000 + update_id,
            "date": 1718000000,
            "chat": {"id": 555},
            "from": {"id": 4242, "first_name": "Yu", "username": "yu"},
            "text": text,
        },
    }


def _photo_update(update_id: int, *, caption: str | None = None) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 2000 + update_id,
            "date": 1718000000,
            "chat": {"id": 555},
            "from": {"id": 4242, "first_name": "Yu", "username": "yu"},
            # PhotoSizes are ordered small→large; the largest must be chosen.
            "photo": [
                {"file_id": "small", "file_size": 100},
                {"file_id": "big", "file_size": 9999},
            ],
            "caption": caption,
        },
    }


@pytest.mark.acceptance(
    spec="channels",
    scenario="an inbound photo is downloaded and drives a turn",
)
async def test_photo_message_is_downloaded_as_an_attachment(
    fake_telegram: FakeTelegram, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))  # media dir resolves under tmp
    adapter = make_telegram_adapter(fake_telegram)
    recorder = RecordingCallbacks()
    await fake_telegram.update_batches.put([_photo_update(20, caption="what is this?")])
    await adapter.start(recorder.as_callbacks())
    try:
        await wait_until(lambda: len(recorder.messages) == 1)
    finally:
        await adapter.stop()

    msg = recorder.messages[0]
    assert msg.text == "what is this?"  # a media caption becomes the message text
    assert len(msg.attachments) == 1
    att = msg.attachments[0]
    assert att.mime == "image/jpeg"
    assert pathlib.Path(att.path).read_bytes() == fake_telegram.file_bytes
    # getFile was called for the LARGEST photo size, not the thumbnail.
    assert [c.get("file_id") for c in fake_telegram.calls_for("getFile")] == ["big"]


def _album_update(update_id: int, *, media_group_id: str, caption: str | None = None) -> dict:
    """One item of a Telegram album — a photo message carrying a shared
    ``media_group_id`` (the caption rides only the first item)."""
    update = _photo_update(update_id, caption=caption)
    update["message"]["media_group_id"] = media_group_id
    # A distinct file per item so the flushed turn's attachments are traceable.
    update["message"]["photo"] = [{"file_id": f"a{update_id}", "file_size": 9999}]
    return update


@pytest.mark.acceptance(
    spec="channels",
    scenario="a Telegram album is handled as one turn",
)
async def test_album_debounces_to_one_turn_with_all_attachments(
    fake_telegram: FakeTelegram, tmp_path, monkeypatch
) -> None:
    """FR-038: three photos sharing one media_group_id (caption on the first)
    debounce into EXACTLY ONE turn carrying all three attachments + the caption,
    not one turn per photo."""
    monkeypatch.setenv("HOME", str(tmp_path))  # media dir resolves under tmp
    # Small debounce so the test is fast (read at adapter construction below).
    monkeypatch.setattr("coffer.infrastructure.channel.telegram._ALBUM_DEBOUNCE_SECONDS", 0.2)
    adapter = make_telegram_adapter(fake_telegram)
    recorder = RecordingCallbacks()
    await fake_telegram.update_batches.put(
        [
            _album_update(60, media_group_id="mg-1", caption="three shots"),
            _album_update(61, media_group_id="mg-1"),
            _album_update(62, media_group_id="mg-1"),
        ]
    )
    await adapter.start(recorder.as_callbacks())
    try:
        await wait_until(lambda: len(recorder.messages) == 1)
        # No SECOND turn ever materializes after the flush.
        await asyncio.sleep(0.4)
        assert len(recorder.messages) == 1
    finally:
        await adapter.stop()

    msg = recorder.messages[0]
    assert msg.text == "three shots"  # caption from the first item drives the turn
    assert len(msg.attachments) == 3  # all three album photos on one message
    assert all(att.mime == "image/jpeg" for att in msg.attachments)
    # getFile was called once per album item's largest photo.
    assert sorted(c.get("file_id") for c in fake_telegram.calls_for("getFile")) == [
        "a60",
        "a61",
        "a62",
    ]


async def test_single_photo_without_media_group_id_dispatches_immediately(
    fake_telegram: FakeTelegram, tmp_path, monkeypatch
) -> None:
    """FR-038: a lone photo (no media_group_id) is NOT debounced — it drives a
    turn immediately, exactly as before."""
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = make_telegram_adapter(fake_telegram)
    recorder = RecordingCallbacks()
    await fake_telegram.update_batches.put([_photo_update(63, caption="just one")])
    await adapter.start(recorder.as_callbacks())
    try:
        await wait_until(lambda: len(recorder.messages) == 1)
    finally:
        await adapter.stop()
    msg = recorder.messages[0]
    assert msg.text == "just one"
    assert len(msg.attachments) == 1


async def test_two_interleaved_media_groups_flush_as_two_turns(
    fake_telegram: FakeTelegram, tmp_path, monkeypatch
) -> None:
    """FR-038: two different albums interleaved keep separate buffers — each
    flushes its own turn with only its own attachments."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("coffer.infrastructure.channel.telegram._ALBUM_DEBOUNCE_SECONDS", 0.2)
    adapter = make_telegram_adapter(fake_telegram)
    recorder = RecordingCallbacks()
    await fake_telegram.update_batches.put(
        [
            _album_update(70, media_group_id="mg-a", caption="album A"),
            _album_update(71, media_group_id="mg-b", caption="album B"),
            _album_update(72, media_group_id="mg-a"),
            _album_update(73, media_group_id="mg-b"),
        ]
    )
    await adapter.start(recorder.as_callbacks())
    try:
        await wait_until(lambda: len(recorder.messages) == 2)
        await asyncio.sleep(0.4)
        assert len(recorder.messages) == 2  # no extra turns
    finally:
        await adapter.stop()
    by_caption = {m.text: m for m in recorder.messages}
    assert set(by_caption) == {"album A", "album B"}
    assert len(by_caption["album A"].attachments) == 2
    assert len(by_caption["album B"].attachments) == 2


async def test_poll_loop_dispatches_and_commits_offset_after_dispatch(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    recorder = RecordingCallbacks()
    await fake_telegram.update_batches.put([_message_update(10, text="hello")])
    await fake_telegram.update_batches.put([_message_update(11, text="world")])
    await adapter.start(recorder.as_callbacks())
    try:
        await wait_until(lambda: len(recorder.messages) == 2)
        # The poll AFTER each dispatched batch must carry update_id + 1.
        await wait_until(
            lambda: (
                [p.get("offset") for p in fake_telegram.calls_for("getUpdates")][:3]
                == [None, 11, 12]
            )
        )
    finally:
        await adapter.stop()

    # getMe comes first and IS awaited: parsing a group message needs the bot's
    # own id, so the poll must not start before the identity is known.
    assert fake_telegram.calls[0][0] == "getMe"
    # The command menu is still registered, just off the startup path.
    registered = {c["command"] for c in fake_telegram.calls_for("setMyCommands")[0]["commands"]}
    assert registered >= {"new", "agent", "model", "stop", "status", "help"}

    msg = recorder.messages[0]
    assert (msg.channel, msg.chat_id, msg.text) == ("tg", "555", "hello")
    assert msg.sender_display == "Yu"
    assert msg.sender_id == "4242"  # from.id, for the owner gate
    assert msg.platform_message_id == "1010"
    assert msg.timestamp.year == 2024  # epoch 1718000000 normalized to aware UTC


async def test_redelivered_update_id_is_processed_once(fake_telegram: FakeTelegram) -> None:
    """FR-039: the poll offset normally prevents replays, but a reconnect race
    can re-deliver an update. The same update_id delivered twice must drive the
    turn once — a redelivered message never doubles the reply."""
    adapter = make_telegram_adapter(fake_telegram)
    recorder = RecordingCallbacks()
    # Two batches carrying the SAME update_id (a redelivery), then a distinct
    # one so the test can wait for a stable end state.
    await fake_telegram.update_batches.put([_message_update(50, text="once")])
    await fake_telegram.update_batches.put([_message_update(50, text="once")])
    await fake_telegram.update_batches.put([_message_update(51, text="next")])
    await adapter.start(recorder.as_callbacks())
    try:
        await wait_until(lambda: [m.text for m in recorder.messages] == ["once", "next"])
    finally:
        await adapter.stop()
    # The duplicate 50 was dropped: exactly one "once", never two.
    assert [m.text for m in recorder.messages] == ["once", "next"]


async def test_poll_error_backs_off_then_recovers(fake_telegram: FakeTelegram) -> None:
    fake_telegram.fail_get_updates = 1  # one 500 → one 1s backoff step, then recovery
    adapter = make_telegram_adapter(fake_telegram)
    recorder = RecordingCallbacks()
    await fake_telegram.update_batches.put([_message_update(7, text="after recovery")])
    await adapter.start(recorder.as_callbacks())
    try:
        await wait_until(lambda: len(recorder.messages) == 1, timeout=8.0)
    finally:
        await adapter.stop()
    assert recorder.messages[0].text == "after recovery"
    assert len(fake_telegram.calls_for("getUpdates")) >= 2  # failed poll + retried poll


@pytest.mark.acceptance(spec="channels", scenario="a long reply is chunked for the platform")
async def test_long_reply_is_chunked_on_paragraph_boundary(fake_telegram: FakeTelegram) -> None:
    para1 = ("alpha " * 500).strip()  # 2999 chars
    para2 = ("bravo " * 500).strip()
    adapter = make_telegram_adapter(fake_telegram)
    try:
        sent = await adapter.send_text("555", f"{para1}\n\n{para2}")
    finally:
        await adapter.stop()
    sends = fake_telegram.calls_for("sendMessage")
    assert len(sends) == 2  # > 4000 chars total → two messages
    assert sends[0]["text"] == para1  # split exactly on the paragraph boundary,
    assert sends[1]["text"] == para2  # delivered in order
    assert all(len(s["text"]) <= 4000 for s in sends)
    assert sent.message_id == "102"  # handle of the LAST delivered chunk


@pytest.mark.acceptance(
    spec="channels", scenario="markdown rendering degrades by channel capability"
)
async def test_markdown_renders_html_falls_back_to_plain_and_seatalk_keeps_markdown(
    fake_telegram: FakeTelegram, fake_seatalk: FakeSeaTalk
) -> None:
    markdown = "**bold** and `code`"

    # Telegram: rich text as HTML parse_mode; on rejection retry as plain text.
    fake_telegram.reject_html_sends = 1
    tg = make_telegram_adapter(fake_telegram)
    try:
        await tg.send_text("555", markdown)
    finally:
        await tg.stop()
    sends = fake_telegram.calls_for("sendMessage")
    assert len(sends) == 2
    assert sends[0]["parse_mode"] == "HTML"
    assert "<b>bold</b>" in sends[0]["text"]
    assert "<code>code</code>" in sends[0]["text"]
    assert "parse_mode" not in sends[1]  # degraded retry: plain text,
    assert sends[1]["text"] == markdown  # original markdown untouched

    # SeaTalk: same input goes out in its declared format (markdown, format=1).
    st = make_seatalk_adapter(fake_seatalk)
    try:
        await st.send_text("emp-1", markdown)
    finally:
        await st.stop()
    body, _auth = fake_seatalk.single_chat_calls[0]
    assert body["message"] == {"tag": "text", "text": {"format": 1, "content": markdown}}


async def test_send_failure_after_plain_retry_raises(fake_telegram: FakeTelegram) -> None:
    fake_telegram.reject_all_sends = 2  # HTML attempt AND the plain retry both refused
    adapter = make_telegram_adapter(fake_telegram)
    try:
        with pytest.raises(ChannelSendFailed):
            await adapter.send_text("555", "hi")
    finally:
        await adapter.stop()
    assert len(fake_telegram.calls_for("sendMessage")) == 2


async def test_non_json_upstream_surfaces_as_channel_send_failed(
    fake_telegram: FakeTelegram,
) -> None:
    # A gateway 502 returns an HTML page, not the Bot API JSON envelope. The
    # raw json() would raise JSONDecodeError (NOT an httpx.HTTPError), escaping
    # the ChannelSendFailed contract; the adapter must translate it.
    fake_telegram.html_error_sends = 1
    adapter = make_telegram_adapter(fake_telegram)
    try:
        with pytest.raises(ChannelSendFailed):
            await adapter.send_text("555", "hi")
    finally:
        await adapter.stop()


async def test_outbound_methods_map_to_bot_api_calls(fake_telegram: FakeTelegram) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    try:
        await adapter.edit_text("555", "10", "edited")
        await adapter.delete_message("555", "10")
        await adapter.send_typing("555")
    finally:
        await adapter.stop()

    edits = fake_telegram.calls_for("editMessageText")
    assert edits[0] == {"chat_id": "555", "message_id": "10", "text": "edited"}
    assert fake_telegram.calls_for("deleteMessage") == [{"chat_id": "555", "message_id": "10"}]
    assert fake_telegram.calls_for("sendChatAction") == [{"chat_id": "555", "action": "typing"}]


# -- group / thread send (Task 4) --------------------------------------------


async def test_send_text_with_thread_id_includes_message_thread_id(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    try:
        await adapter.send_text("555", "hi", thread_id="9")
    finally:
        await adapter.stop()
    [send] = fake_telegram.calls_for("sendMessage")
    assert send["message_thread_id"] == 9


async def test_send_text_without_thread_id_omits_message_thread_id(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    try:
        await adapter.send_text("555", "hi")
    finally:
        await adapter.stop()
    [send] = fake_telegram.calls_for("sendMessage")
    assert "message_thread_id" not in send


async def test_send_media_with_thread_id_includes_message_thread_id(
    fake_telegram: FakeTelegram, tmp_path: pathlib.Path
) -> None:
    """FR-031: a file returned during a forum-topic turn is uploaded into that
    topic — sendPhoto carries ``message_thread_id`` (mirroring send_text)."""
    img = tmp_path / "chart.png"
    img.write_bytes(b"PNG")
    adapter = make_telegram_adapter(fake_telegram)
    try:
        await adapter.send_media("555", str(img), as_photo=True, thread_id="9")
    finally:
        await adapter.stop()
    [send] = fake_telegram.calls_for("sendPhoto")
    assert send["chat_id"] == "555"
    assert send["message_thread_id"] == "9"


async def test_send_media_without_thread_id_omits_message_thread_id(
    fake_telegram: FakeTelegram, tmp_path: pathlib.Path
) -> None:
    doc = tmp_path / "report.pdf"
    doc.write_bytes(b"%PDF")
    adapter = make_telegram_adapter(fake_telegram)
    try:
        await adapter.send_media("555", str(doc), as_photo=False)
    finally:
        await adapter.stop()
    [send] = fake_telegram.calls_for("sendDocument")
    assert "message_thread_id" not in send


async def test_send_text_chat_kind_group_is_ignored(fake_telegram: FakeTelegram) -> None:
    # Telegram routes DMs and groups through the same chat_id; chat_kind is a
    # no-op here (unlike SeaTalk, which needs it to pick the endpoint).
    adapter = make_telegram_adapter(fake_telegram)
    try:
        await adapter.send_text("555", "hi", chat_kind="group")
    finally:
        await adapter.stop()
    [send] = fake_telegram.calls_for("sendMessage")
    assert send["chat_id"] == "555"


async def test_capabilities_declare_groups_but_not_history_fetch(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    try:
        assert adapter.capabilities.supports_groups is True
        assert adapter.capabilities.supports_history_fetch is False
    finally:
        await adapter.stop()


def _callback_update(update_id: int, *, data: str) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "cbq-1",
            "from": {"id": 4242, "first_name": "Yu"},
            "data": data,
            "message": {"message_id": 77, "chat": {"id": 555}},
        },
    }


async def test_send_text_with_buttons_emits_inline_keyboard(fake_telegram: FakeTelegram) -> None:
    from coffer.domain.channel.envelopes import ChoiceButton

    adapter = make_telegram_adapter(fake_telegram)
    try:
        await adapter.send_text(
            "555",
            "Pick an agent:",
            buttons=[
                ChoiceButton(label="Claude Code", value="agent:claude_code"),
                ChoiceButton(label="Codex", value="agent:codex"),
            ],
        )
    finally:
        await adapter.stop()

    sent = fake_telegram.calls_for("sendMessage")[-1]
    assert sent["reply_markup"] == {
        "inline_keyboard": [
            [{"text": "Claude Code", "callback_data": "agent:claude_code"}],
            [{"text": "Codex", "callback_data": "agent:codex"}],
        ]
    }


async def test_callback_query_routes_to_on_callback_and_acks(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    recorder = RecordingCallbacks()
    await fake_telegram.update_batches.put([_callback_update(20, data="model:opus")])
    await adapter.start(recorder.as_callbacks())
    try:
        await wait_until(lambda: len(recorder.callbacks) == 1)
        await wait_until(lambda: len(fake_telegram.calls_for("answerCallbackQuery")) == 1)
    finally:
        await adapter.stop()

    cb = recorder.callbacks[0]
    assert (cb.channel, cb.chat_id, cb.sender_id, cb.data) == ("tg", "555", "4242", "model:opus")
    assert cb.callback_id == "cbq-1"
    assert cb.platform_message_id == "77"
    # The ack carries the choice back as an instant bubble, not just a spinner
    # dismissal, so a tap is acknowledged before the card rewrite lands.
    assert fake_telegram.calls_for("answerCallbackQuery")[0] == {
        "callback_query_id": "cbq-1",
        "text": "✓ opus",
    }
    # The poll must subscribe to callback_query, else Telegram never delivers taps.
    assert "callback_query" in fake_telegram.calls_for("getUpdates")[0]["allowed_updates"]
    # A tap whose card sits in a private chat routes as a direct reply.
    assert cb.chat_kind == "direct"
    assert cb.thread_id == ""


async def test_callback_query_from_supergroup_routes_as_group_callback(
    fake_telegram: FakeTelegram,
) -> None:
    """FR-034: a card tapped in a supergroup forum topic yields a group callback
    (chat_kind="group" + the topic's message_thread_id) so the switch reply
    lands back in the group thread, not a DM."""
    adapter = make_telegram_adapter(fake_telegram)
    recorder = RecordingCallbacks()
    await fake_telegram.update_batches.put(
        [
            {
                "update_id": 21,
                "callback_query": {
                    "id": "cbq-2",
                    "from": {"id": 4242, "first_name": "Yu"},
                    "data": "agent:codex",
                    "message": {
                        "message_id": 88,
                        "chat": {"id": 777, "type": "supergroup"},
                        "message_thread_id": 9,
                    },
                },
            }
        ]
    )
    await adapter.start(recorder.as_callbacks())
    try:
        await wait_until(lambda: len(recorder.callbacks) == 1)
    finally:
        await adapter.stop()

    cb = recorder.callbacks[0]
    assert (cb.chat_id, cb.data) == ("777", "agent:codex")
    assert cb.chat_kind == "group"
    assert cb.thread_id == "9"


async def test_buttons_ride_only_the_final_chunk(fake_telegram: FakeTelegram) -> None:
    from coffer.domain.channel.envelopes import ChoiceButton

    adapter = make_telegram_adapter(fake_telegram)
    long_md = ("a" * 3000) + "\n\n" + ("b" * 3000)  # two paragraphs → two chunks
    try:
        await adapter.send_text(
            "555", long_md, buttons=[ChoiceButton(label="Codex", value="agent:codex")]
        )
    finally:
        await adapter.stop()

    sends = fake_telegram.calls_for("sendMessage")
    assert len(sends) >= 2
    assert "reply_markup" not in sends[0]  # the keyboard must not ride the first chunk
    assert "reply_markup" in sends[-1]  # only the last chunk carries it


# -- context fetch (Task 5): Bot API has no history-fetch capability ----------


async def test_fetch_thread_returns_empty(fake_telegram: FakeTelegram) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    try:
        assert await adapter.fetch_thread("555", "t1", limit=50) == ([], ())
    finally:
        await adapter.stop()
    assert fake_telegram.calls == []  # no platform call is even attempted


# -- group / @mention / reply / forward / forum-topic (Task 8) ---------------

_BOT_ID = 999
_BOT_USERNAME = "mybot"


async def _start_bot_adapter(fake: FakeTelegram, recorder: RecordingCallbacks) -> TelegramAdapter:
    """Start a telegram adapter and pin its bot identity, as if getMe() had
    resolved it — set right after start() so the fake's empty getMe response
    doesn't clobber it, and before any await lets the poll task run."""
    adapter = make_telegram_adapter(fake)
    await adapter.start(recorder.as_callbacks())
    adapter._identity = BotIdentity(bot_id=_BOT_ID, username=_BOT_USERNAME)
    return adapter


def _group_update(update_id: int, **overrides) -> dict:
    message = {
        "message_id": 3000 + update_id,
        "date": 1718000000,
        "chat": {"id": 777, "type": "group"},
        "from": {"id": 4242, "first_name": "Yu", "username": "yu"},
        "text": "hello",
    }
    message.update(overrides)
    return {"update_id": update_id, "message": message}


async def test_group_message_without_mention_is_not_addressed(fake_telegram: FakeTelegram) -> None:
    recorder = RecordingCallbacks()
    adapter = await _start_bot_adapter(fake_telegram, recorder)
    await fake_telegram.update_batches.put([_group_update(30, text="just chatting")])
    try:
        await wait_until(lambda: len(recorder.messages) == 1)
    finally:
        await adapter.stop()
    msg = recorder.messages[0]
    assert msg.chat_kind == "group"
    assert msg.addressed is False
    assert msg.text == "just chatting"


async def test_group_message_with_mention_entity_is_addressed_and_stripped(
    fake_telegram: FakeTelegram,
) -> None:
    recorder = RecordingCallbacks()
    adapter = await _start_bot_adapter(fake_telegram, recorder)
    text = "@mybot run"
    await fake_telegram.update_batches.put(
        [
            _group_update(
                31,
                text=text,
                entities=[{"type": "mention", "offset": 0, "length": len("@mybot")}],
            )
        ]
    )
    try:
        await wait_until(lambda: len(recorder.messages) == 1)
    finally:
        await adapter.stop()
    msg = recorder.messages[0]
    assert msg.chat_kind == "group"
    assert msg.addressed is True
    assert msg.text == "run"


async def test_group_reply_to_bot_is_addressed(fake_telegram: FakeTelegram) -> None:
    recorder = RecordingCallbacks()
    adapter = await _start_bot_adapter(fake_telegram, recorder)
    await fake_telegram.update_batches.put(
        [
            _group_update(
                32,
                text="yes please",
                reply_to_message={
                    "from": {"id": _BOT_ID, "is_bot": True, "username": _BOT_USERNAME},
                    "text": "which agent?",
                },
            )
        ]
    )
    try:
        await wait_until(lambda: len(recorder.messages) == 1)
    finally:
        await adapter.stop()
    msg = recorder.messages[0]
    assert msg.addressed is True
    # The quoted reply-to-bot context is folded into the text.
    assert msg.text.splitlines()[0] == "> mybot: which agent?"
    assert msg.text.splitlines()[-1] == "yes please"


async def test_forum_topic_message_carries_thread_id(fake_telegram: FakeTelegram) -> None:
    recorder = RecordingCallbacks()
    adapter = await _start_bot_adapter(fake_telegram, recorder)
    await fake_telegram.update_batches.put(
        [_group_update(33, text="topic reply", message_thread_id=9)]
    )
    try:
        await wait_until(lambda: len(recorder.messages) == 1)
    finally:
        await adapter.stop()
    msg = recorder.messages[0]
    assert msg.thread_id == "9"


@pytest.mark.acceptance(spec="channels", scenario="a forwarded chat record reaches the agent")
async def test_forwarded_message_text_starts_with_forwarded_marker(
    fake_telegram: FakeTelegram,
) -> None:
    recorder = RecordingCallbacks()
    adapter = await _start_bot_adapter(fake_telegram, recorder)
    await fake_telegram.update_batches.put(
        [
            _group_update(
                35,
                text="original text",
                forward_from={"first_name": "Alice"},
            )
        ]
    )
    try:
        await wait_until(lambda: len(recorder.messages) == 1)
    finally:
        await adapter.stop()
    msg = recorder.messages[0]
    assert msg.text.startswith("[Forwarded chat record]")
    assert "Alice: original text" in msg.text


async def test_private_message_is_direct_and_always_addressed(fake_telegram: FakeTelegram) -> None:
    recorder = RecordingCallbacks()
    adapter = await _start_bot_adapter(fake_telegram, recorder)
    await fake_telegram.update_batches.put(
        [
            {
                "update_id": 36,
                "message": {
                    "message_id": 3036,
                    "date": 1718000000,
                    "chat": {"id": 555, "type": "private"},
                    "from": {"id": 4242, "first_name": "Yu", "username": "yu"},
                    "text": "hi there",
                },
            }
        ]
    )
    try:
        await wait_until(lambda: len(recorder.messages) == 1)
    finally:
        await adapter.stop()
    msg = recorder.messages[0]
    assert msg.chat_kind == "direct"
    assert msg.addressed is True
    assert msg.text == "hi there"


async def test_a_non_list_getupdates_result_backs_off_instead_of_spinning(
    fake_telegram: FakeTelegram,
) -> None:
    """Regression: the ``ok: true`` / non-list-result branch used to ``continue``
    with no delay, so a payload the Bot API kept returning span the poll task —
    and with it the daemon's whole event loop — at 100% CPU. It now backs off on
    the same ladder a raised failure uses."""
    fake_telegram.bad_payload_get_updates = True
    adapter = make_telegram_adapter(fake_telegram)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await asyncio.sleep(0.5)
    finally:
        await adapter.stop()

    # The first ladder rung is 1s, so half a second of polling is one call —
    # a couple more would still prove the point; hundreds would be the old spin.
    assert len(fake_telegram.calls_for("getUpdates")) <= 3


# -- live text: the editable surface (FR-037) ---------------------------------


async def test_live_text_sends_once_then_edits_and_deletes_on_close(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    try:
        assert adapter.capabilities.supports_live_text is True
        live = TelegramLiveText(adapter._call, "555", now=_live_ticking())
        await live.update("I found")
        await live.update("I found three cats.")
        leftover = await live.close("I found three cats.")
    finally:
        await adapter.stop()

    sends = fake_telegram.calls_for("sendMessage")
    assert len(sends) == 1  # opened once…
    assert sends[0]["text"] == "I found"
    assert "parse_mode" not in sends[0]  # interim text is PLAIN, never HTML
    edits = fake_telegram.calls_for("editMessageText")
    assert [e["text"] for e in edits] == ["I found three cats."]  # …then edited in place
    # The status message is scaffolding: it is deleted and the whole reply is
    # handed back, so the caller sends it HTML-rendered and chunked.
    assert fake_telegram.calls_for("deleteMessage") == [{"chat_id": "555", "message_id": "101"}]
    assert leftover == "I found three cats."


async def test_live_text_stops_writing_once_the_platform_rejects_an_update(
    fake_telegram: FakeTelegram,
) -> None:
    fake_telegram.reject_all_sends = 1  # the very first snapshot is refused
    adapter = make_telegram_adapter(fake_telegram)
    try:
        live = TelegramLiveText(adapter._call, "555", now=_live_ticking())
        await live.update("one")
        await live.update("one two")  # the surface is dead — nothing more is sent
        leftover = await live.close("one two three")
    finally:
        await adapter.stop()

    assert len(fake_telegram.calls_for("sendMessage")) == 1
    assert fake_telegram.calls_for("editMessageText") == []
    assert fake_telegram.calls_for("deleteMessage") == []  # nothing to delete
    assert leftover == "one two three"  # the reply still owes the user its text


# -- Bot API 10.x parity: profile, reply routing, media coverage ---------------


async def test_start_registers_the_full_command_menu(fake_telegram: FakeTelegram) -> None:
    """FR-065: the menu the platform shows lists every command that exists."""
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        # Registration runs off the startup path, so the reconciler is not held
        # up by calls nothing depends on — wait for it rather than racing it.
        await wait_until(lambda: len(fake_telegram.calls_for("setMyCommands")) == 1)
        await wait_until(lambda: bool(fake_telegram.calls_for("setChatMenuButton")))
        registered = fake_telegram.calls_for("setMyCommands")
        assert len(registered) == 1
        names = {entry["command"] for entry in registered[0]["commands"]}
        assert names == {"new", "agent", "model", "stop", "status", "help"}
        assert fake_telegram.calls_for("setChatMenuButton")[0]["menu_button"] == {
            "type": "commands"
        }
    finally:
        await adapter.stop()


async def test_start_probes_identity_including_privacy_mode(
    fake_telegram: FakeTelegram,
) -> None:
    """FR-059/FR-060: privacy mode is read at start-up, not assumed."""
    fake_telegram.results["getMe"] = {
        "id": 4242,
        "username": "cofferbot",
        "can_read_all_group_messages": False,
    }
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        assert adapter.identity == BotIdentity(
            bot_id=4242, username="cofferbot", reads_all_group_messages=False
        )
    finally:
        await adapter.stop()


@pytest.mark.acceptance(
    spec="channels", scenario="a group reply is attached to the message it answers"
)
async def test_group_reply_carries_reply_parameters(fake_telegram: FakeTelegram) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text("555", "here you go", chat_kind="group", reply_to_message_id="31")
    finally:
        await adapter.stop()
    sent = fake_telegram.calls_for("sendMessage")[0]
    assert sent["reply_parameters"] == {
        "message_id": 31,
        "allow_sending_without_reply": True,
    }


async def test_a_send_without_a_reply_target_carries_no_reply_parameters(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text("555", "plain")
    finally:
        await adapter.stop()
    assert "reply_parameters" not in fake_telegram.calls_for("sendMessage")[0]


async def test_only_the_first_chunk_answers_the_user_message(
    fake_telegram: FakeTelegram,
) -> None:
    # A reply pointer on every chunk would make one answer look like five.
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text(
            "555", "\n\n".join("x" * 3000 for _ in range(3)), reply_to_message_id="9"
        )
    finally:
        await adapter.stop()
    sends = fake_telegram.calls_for("sendMessage")
    assert len(sends) >= 2
    assert "reply_parameters" in sends[0]
    assert all("reply_parameters" not in send for send in sends[1:])


async def test_typing_action_can_say_what_is_being_uploaded(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_typing("555", action="upload_document")
    finally:
        await adapter.stop()
    assert fake_telegram.calls_for("sendChatAction")[0]["action"] == "upload_document"


@pytest.mark.acceptance(spec="channels", scenario="an oversized inbound file tells the user")
async def test_oversized_attachment_is_reported_in_the_turn_text(
    fake_telegram: FakeTelegram, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    recorder = RecordingCallbacks()
    adapter = make_telegram_adapter(fake_telegram, media_dir=tmp_path / "media")
    await adapter.start(recorder.as_callbacks())
    await fake_telegram.update_batches.put(
        [
            {
                "update_id": 90,
                "message": {
                    "message_id": 9000,
                    "date": 1718000000,
                    "chat": {"id": 555},
                    "from": {"id": 4242, "first_name": "Yu"},
                    "caption": "have a look",
                    "document": {
                        "file_id": "huge",
                        "file_name": "dump.sql",
                        "file_size": 30 * 1024 * 1024,
                    },
                },
            }
        ]
    )
    try:
        await wait_until(lambda: len(recorder.messages) == 1)
    finally:
        await adapter.stop()
    text = recorder.messages[0].text
    assert "have a look" in text
    assert "dump.sql" in text and "did not reach the agent" in text


async def test_a_removal_reaches_the_lifecycle_callback(fake_telegram: FakeTelegram) -> None:
    """FR-058: a removal must arrive, which means it must be subscribed to —
    Telegram withholds my_chat_member unless it is named in allowed_updates."""
    recorder = RecordingCallbacks()
    adapter = await _start_bot_adapter(fake_telegram, recorder)
    await fake_telegram.update_batches.put(
        [
            {
                "update_id": 70,
                "my_chat_member": {
                    "chat": {"id": -100123, "type": "supergroup"},
                    "new_chat_member": {
                        "user": {"id": _BOT_ID, "is_bot": True},
                        "status": "kicked",
                    },
                },
            }
        ]
    )
    try:
        await wait_until(lambda: len(recorder.lifecycles) == 1)
    finally:
        await adapter.stop()
    event = recorder.lifecycles[0]
    assert (event.channel, event.chat_id, event.kind) == ("tg", "-100123", "removed_from_group")
    assert "my_chat_member" in fake_telegram.calls_for("getUpdates")[0]["allowed_updates"]


# -- rich messages (FR-061) ---------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="a rich reply keeps its markdown structure")
async def test_a_rich_reply_keeps_headings_lists_and_tables(fake_telegram: FakeTelegram) -> None:
    fake_telegram.supports_rich = True
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    body = "## Results\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    try:
        await adapter.send_text("555", body)
    finally:
        await adapter.stop()
    assert not fake_telegram.calls_for("sendMessage")
    sent = fake_telegram.calls_for("sendRichMessage")[0]
    # The structure the HTML subset destroyed — heading, bullets, table — is
    # handed to the platform exactly as the agent wrote it.
    assert sent["rich_message"]["markdown"] == body


async def test_a_platform_without_rich_messages_still_delivers_the_reply(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)  # fake defaults to pre-10.1
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text("555", "## Results\n\n- one")
    finally:
        await adapter.stop()
    assert len(fake_telegram.calls_for("sendRichMessage")) == 1  # tried once
    assert "Results" in fake_telegram.calls_for("sendMessage")[0]["text"]


async def test_an_unsupported_rich_send_is_tried_only_once(fake_telegram: FakeTelegram) -> None:
    """FR-059: latched off for the process, not retried before every reply."""
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text("555", "first")
        await adapter.send_text("555", "second")
        await adapter.send_text("555", "third")
    finally:
        await adapter.stop()
    assert len(fake_telegram.calls_for("sendRichMessage")) == 1
    assert len(fake_telegram.calls_for("sendMessage")) == 3


async def test_the_chunk_budget_drops_when_rich_messages_latch_off(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    assert adapter.capabilities.max_message_chars == 32000
    try:
        await adapter.send_text("555", "hello")
    finally:
        await adapter.stop()
    # A 32k chunk would be refused by an ordinary sendMessage, so the budget
    # must follow the feature down.
    assert adapter.capabilities.max_message_chars == 4000


async def test_a_rejected_rich_message_does_not_latch_the_feature_off(
    fake_telegram: FakeTelegram,
) -> None:
    # "can't parse entities" is about THIS message, not about the server's
    # abilities — disabling rich messages over one bad table would be wrong.
    fake_telegram.supports_rich = True
    fake_telegram.reject_all_sends = 1
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text("555", "bad | table")
        await adapter.send_text("555", "fine")
    finally:
        await adapter.stop()
    assert len(fake_telegram.calls_for("sendRichMessage")) == 2
    assert adapter.capabilities.max_message_chars == 32000


async def test_a_rich_send_carries_buttons_and_the_reply_pointer(
    fake_telegram: FakeTelegram,
) -> None:
    fake_telegram.supports_rich = True
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text(
            "555",
            "pick one",
            buttons=[ChoiceButton(label="Codex", value="agent:codex")],
            title="Agent",
            chat_kind="group",
            reply_to_message_id="31",
        )
    finally:
        await adapter.stop()
    sent = fake_telegram.calls_for("sendRichMessage")[0]
    assert sent["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "agent:codex"
    assert sent["reply_parameters"]["message_id"] == 31
    # A rich message has real headings, so the title is one rather than a bold line.
    assert sent["rich_message"]["markdown"].startswith("## Agent")


# -- streamed drafts and the platform stop control (FR-062 / FR-063) ----------


async def test_a_live_reply_streams_as_a_draft(fake_telegram: FakeTelegram) -> None:
    fake_telegram.supports_drafts = True
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    surface = await adapter.open_live_text("555")
    assert isinstance(surface, TelegramDraftLiveText)
    try:
        await surface.update("thinking")
        remainder = await surface.close("the whole answer")
    finally:
        await adapter.stop()
    drafts = fake_telegram.calls_for("sendMessageDraft")
    assert [d["text"] for d in drafts] == ["thinking"]
    assert drafts[0]["draft_id"] == surface.draft_id
    # A draft is a preview, never the reply: the caller still sends the real
    # message, and there is nothing to clean up.
    assert remainder == "the whole answer"
    assert not fake_telegram.calls_for("deleteMessage")


async def test_a_streamed_draft_advertises_the_stop_control(
    fake_telegram: FakeTelegram,
) -> None:
    fake_telegram.supports_drafts = True
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    surface = await adapter.open_live_text("555", thread_id="8")
    try:
        await surface.update("partial")
    finally:
        await adapter.stop()
    draft = fake_telegram.calls_for("sendMessageDraft")[0]
    assert draft["can_stop"] is True
    # The finished reply is sent straight after, so a kept draft would leave the
    # user reading the answer twice.
    assert draft["keep_on_stop"] is False
    assert draft["message_thread_id"] == 8


async def test_drafts_fall_back_to_the_edited_message_surface(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)  # fake defaults to pre-10.1
    await adapter.start(RecordingCallbacks().as_callbacks())
    first = await adapter.open_live_text("555")
    try:
        await first.update("partial")  # latches drafts off
        second = await adapter.open_live_text("555")
        await second.update("partial")
    finally:
        await adapter.stop()
    # The next turn must not pay for another doomed round trip (FR-059).
    assert isinstance(second, TelegramLiveText)
    assert len(fake_telegram.calls_for("sendMessageDraft")) == 1
    # The edit surface opens by sending the message it will then rewrite.
    assert fake_telegram.calls_for("sendMessage")[0]["text"] == "partial"


@pytest.mark.acceptance(
    spec="channels", scenario="a stop pressed on the platform's own control ends the turn"
)
async def test_the_stop_control_reaches_the_stop_callback(fake_telegram: FakeTelegram) -> None:
    recorder = RecordingCallbacks()
    adapter = await _start_bot_adapter(fake_telegram, recorder)
    await fake_telegram.update_batches.put(
        [
            {
                "update_id": 80,
                "stopped_message_generation": {
                    "chat": {"id": -100123, "type": "supergroup"},
                    "message_thread_id": 8,
                    "draft_id": 4242,
                },
            }
        ]
    )
    try:
        await wait_until(lambda: len(recorder.stops) == 1)
    finally:
        await adapter.stop()
    stop = recorder.stops[0]
    assert (stop.channel, stop.chat_id, stop.thread_id, stop.chat_kind) == (
        "tg",
        "-100123",
        "8",
        "group",
    )
    assert (
        "stopped_message_generation" in fake_telegram.calls_for("getUpdates")[0]["allowed_updates"]
    )


# -- ephemeral group answers (FR-064) -----------------------------------------


async def test_an_ephemeral_answer_is_addressed_to_one_member(
    fake_telegram: FakeTelegram,
) -> None:
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text(
            "-100123",
            "Conversation: conv-1",
            chat_kind="group",
            thread_id="8",
            ephemeral=EphemeralTarget(receiver_id="4242", ephemeral_message_id="77"),
        )
    finally:
        await adapter.stop()
    sent = fake_telegram.calls_for("sendMessage")[0]
    assert sent["ephemeral_message_parameters"] == {"receiver_user_id": 4242}
    assert sent["reply_parameters"]["ephemeral_message_id"] == 77
    assert sent["message_thread_id"] == 8
    # A private answer is a command's reply: one message, not a rich chunked one.
    assert not fake_telegram.calls_for("sendRichMessage")


async def test_a_refused_ephemeral_answer_still_reaches_the_group(
    fake_telegram: FakeTelegram,
) -> None:
    # The worst case must be the noise Coffer already made, never a missing
    # answer, so a refusal falls through to an ordinary send.
    fake_telegram.reject_all_sends = 1
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text(
            "-100123",
            "Conversation: conv-1",
            chat_kind="group",
            ephemeral=EphemeralTarget(receiver_id="4242", ephemeral_message_id="77"),
        )
    finally:
        await adapter.stop()
    sends = fake_telegram.calls_for("sendMessage")
    assert len(sends) == 2
    assert "ephemeral_message_parameters" not in sends[1]
    assert "conv-1" in sends[1]["text"]


async def test_an_ordinary_reply_is_never_ephemeral(fake_telegram: FakeTelegram) -> None:
    # The agent's actual reply is the conversation the group is having.
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text("-100123", "here is the answer", chat_kind="group")
    finally:
        await adapter.stop()
    assert "ephemeral_message_parameters" not in fake_telegram.calls_for("sendMessage")[0]


async def test_a_group_turn_keeps_the_edit_based_surface(fake_telegram: FakeTelegram) -> None:
    """sendMessageDraft addresses "the target private chat" and has no group
    form, so a group turn would spend a refused round trip per snapshot and
    show no progress at all."""
    fake_telegram.supports_drafts = True
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    surface = await adapter.open_live_text("-100123", chat_kind="group", thread_id="8")
    try:
        await surface.update("partial")
    finally:
        await adapter.stop()
    assert isinstance(surface, TelegramLiveText)
    assert not fake_telegram.calls_for("sendMessageDraft")


async def test_a_long_snapshot_keeps_the_draft_alive(fake_telegram: FakeTelegram) -> None:
    """A live snapshot is the whole reply so far, so it outgrows the draft's
    4096-character budget on any long answer. Sending it anyway is refused and
    latches the surface dead — the one thing a progress indicator must not do."""
    fake_telegram.supports_drafts = True
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    surface = await adapter.open_live_text("555")
    try:
        await surface.update("x" * 9000)
    finally:
        await adapter.stop()
    sent = fake_telegram.calls_for("sendMessageDraft")[0]["text"]
    assert len(sent) == 4096
    # The tail is what the reader is watching, not the head they have seen.
    assert sent.startswith("…") and sent.endswith("x")
