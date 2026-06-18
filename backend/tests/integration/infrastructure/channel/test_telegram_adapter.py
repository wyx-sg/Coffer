"""TelegramAdapter against an in-process fake Bot API (no real network).

Covers the long-poll loop (dispatch, offset-after-dispatch, error backoff),
outbound rendering (HTML with plain-text retry, chunking), and the Bot API
method mapping for edit/delete/typing/approval prompts.
"""

from __future__ import annotations

import pytest

from coffer.domain.channel.errors import ChannelSendFailed

from .conftest import (
    FakeSeaTalk,
    FakeTelegram,
    RecordingCallbacks,
    make_seatalk_adapter,
    make_telegram_adapter,
    wait_until,
)


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

    # setMyCommands registered the command menu before polling began.
    assert fake_telegram.calls[0][0] == "setMyCommands"
    registered = {c["command"] for c in fake_telegram.calls[0][1]["commands"]}
    assert registered >= {"new", "stop", "status", "help"}

    msg = recorder.messages[0]
    assert (msg.channel, msg.chat_id, msg.text) == ("tg", "555", "hello")
    assert msg.sender_display == "Yu"
    assert msg.sender_id == "4242"  # from.id, for the owner gate
    assert msg.platform_message_id == "1010"
    assert msg.timestamp.year == 2024  # epoch 1718000000 normalized to aware UTC


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


@pytest.mark.acceptance(spec="009-channels", scenario="a long reply is chunked for the platform")
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
    spec="009-channels", scenario="markdown rendering degrades by channel capability"
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
