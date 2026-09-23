"""Acceptance scenarios of spec channels/telegram, at the transport.

Each test drives a real TelegramAdapter against the in-process fake Bot API
from ``conftest`` and asserts what reaches the wire.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.channel.selection_cards import model_card
from coffer.infrastructure.channel import live_text
from coffer.infrastructure.channel.live_text import TelegramLiveText
from coffer.infrastructure.channel.telegram_draft import TelegramDraftLiveText
from coffer.infrastructure.channel.telegram_profile import BotIdentity

from .conftest import FakeTelegram, RecordingCallbacks, make_telegram_adapter, wait_until

_BOT_ID = 999


def _dm(update_id: int, text: str) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1000 + update_id,
            "date": 1718000000,
            "chat": {"id": 555, "type": "private"},
            "from": {"id": 4242, "first_name": "Yu"},
            "text": text,
        },
    }


@pytest.mark.acceptance(
    spec="channels/telegram",
    scenario="the polling offset advances only past dispatched updates",
)
async def test_the_offset_follows_dispatch_and_a_failed_poll_is_retried(
    fake_telegram: FakeTelegram,
) -> None:
    fake_telegram.fail_get_updates = 1  # the first poll fails
    await fake_telegram.update_batches.put([_dm(10, "a"), _dm(11, "b")])
    await fake_telegram.update_batches.put([_dm(12, "c")])
    recorder = RecordingCallbacks()
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(recorder.as_callbacks())
    try:
        await wait_until(lambda: len(recorder.messages) == 3, timeout=8.0)
        await wait_until(
            lambda: 13 in [p.get("offset") for p in fake_telegram.calls_for("getUpdates")]
        )
    finally:
        await adapter.stop()

    offsets = [p.get("offset") for p in fake_telegram.calls_for("getUpdates")]
    # The failed poll was retried (it asked again from the same place) …
    assert offsets[0] is None and offsets[1] is None
    # … and after each dispatched batch the next poll asks past its last update.
    assert offsets[2:4] == [12, 13]
    assert [m.text for m in recorder.messages] == ["a", "b", "c"]


@pytest.mark.acceptance(
    spec="channels/telegram",
    scenario="getMe identity is kept and a rejected newer surface is latched off",
)
async def test_identity_is_read_and_an_unsupported_surface_latches_off(
    fake_telegram: FakeTelegram,
) -> None:
    fake_telegram.results["getMe"] = {
        "id": _BOT_ID,
        "username": "cofferbot",
        "can_read_all_group_messages": False,
    }
    adapter = make_telegram_adapter(fake_telegram)  # fake server predates rich messages
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        assert adapter.identity == BotIdentity(
            bot_id=_BOT_ID, username="cofferbot", reads_all_group_messages=False
        )
        await adapter.send_text("555", "one")
        await adapter.send_text("555", "two")
        await adapter.send_text("555", "three")
    finally:
        await adapter.stop()
    # Refused as unsupported once, then never attempted again this process.
    assert len(fake_telegram.calls_for("sendRichMessage")) == 1
    assert len(fake_telegram.calls_for("sendMessage")) == 3

    # An ordinary refusal (this message, not the server's abilities) leaves the
    # surface available for the next reply.
    other = FakeTelegram()
    other.supports_rich = True
    other.reject_all_sends = 1
    adapter2 = make_telegram_adapter(other)
    await adapter2.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter2.send_text("555", "bad | table")
        await adapter2.send_text("555", "fine")
    finally:
        await adapter2.stop()
    assert len(other.calls_for("sendRichMessage")) == 2


@pytest.mark.acceptance(
    spec="channels/telegram", scenario="the bot leaving a group arrives as a removal event"
)
async def test_membership_changes_normalize_to_a_removal_only_when_the_bot_left(
    fake_telegram: FakeTelegram,
) -> None:
    fake_telegram.results["getMe"] = {"id": _BOT_ID, "username": "mybot"}

    def membership(update_id: int, user_id: int, status: str) -> dict[str, Any]:
        return {
            "update_id": update_id,
            "my_chat_member": {
                "chat": {"id": -100123, "type": "supergroup"},
                "new_chat_member": {"user": {"id": user_id}, "status": status},
            },
        }

    recorder = RecordingCallbacks()
    adapter = make_telegram_adapter(fake_telegram)
    await fake_telegram.update_batches.put(
        [
            membership(1, 7777, "left"),  # another user left
            membership(2, _BOT_ID, "member"),  # the bot is still in
            membership(3, _BOT_ID, "kicked"),  # the bot was removed
            _dm(4, "sentinel"),
        ]
    )
    await adapter.start(recorder.as_callbacks())
    try:
        await wait_until(lambda: len(recorder.messages) == 1)
    finally:
        await adapter.stop()
    assert "my_chat_member" in fake_telegram.calls_for("getUpdates")[0]["allowed_updates"]
    assert [(e.chat_id, e.kind) for e in recorder.lifecycles] == [("-100123", "removed_from_group")]


@pytest.mark.acceptance(
    spec="channels/telegram",
    scenario="a reply is sent as telegram HTML and retried as plain text when refused",
)
async def test_a_long_reply_is_html_chunked_and_a_refused_chunk_is_resent_plain(
    fake_telegram: FakeTelegram,
) -> None:
    para1 = "**bold** " + ("alpha " * 480).strip()
    para2 = "**also** " + ("bravo " * 480).strip()
    assert len(para1) + len(para2) > 4000
    fake_telegram.reject_html_sends = 1  # the first HTML chunk is refused
    adapter = make_telegram_adapter(fake_telegram)
    try:
        await adapter.send_text("555", f"{para1}\n\n{para2}")
    finally:
        await adapter.stop()
    sends = fake_telegram.calls_for("sendMessage")
    assert all(len(s["text"]) <= 4000 for s in sends)
    first_html, first_plain, second = sends
    assert first_html["parse_mode"] == "HTML" and "<b>bold</b>" in first_html["text"]
    assert "parse_mode" not in first_plain  # the refused chunk re-sent as plain text
    assert "alpha" in first_plain["text"] and "bravo" not in first_plain["text"]
    assert second["parse_mode"] == "HTML" and "<b>also</b>" in second["text"]
    assert "alpha" not in second["text"]  # split on the paragraph boundary


@pytest.mark.acceptance(
    spec="channels/telegram", scenario="a structured reply is sent as a telegram rich message"
)
async def test_a_structured_reply_goes_out_as_rich_or_falls_back_to_html(
    fake_telegram: FakeTelegram,
) -> None:
    body = "## Results\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    fake_telegram.supports_rich = True
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text("555", body)
    finally:
        await adapter.stop()
    assert fake_telegram.calls_for("sendRichMessage")[0]["rich_message"]["markdown"] == body
    assert fake_telegram.calls_for("sendMessage") == []

    older = FakeTelegram()  # refuses rich messages as unknown
    adapter2 = make_telegram_adapter(older)
    await adapter2.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter2.send_text("555", body)
    finally:
        await adapter2.stop()
    [html] = older.calls_for("sendMessage")
    assert html["parse_mode"] == "HTML"
    assert "Results" in html["text"]


@pytest.mark.acceptance(
    spec="channels/telegram",
    scenario=(
        "a direct-chat turn streams into a message draft while a group turn edits a status message"
    ),
)
async def test_drafts_stream_dms_while_groups_edit_a_status_message(
    fake_telegram: FakeTelegram, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No throttle, so the group's second snapshot is written as an edit now
    # rather than dropped for arriving inside the 1.5 s window.
    monkeypatch.setattr(live_text, "TELEGRAM_UPDATE_INTERVAL", 0.0)
    fake_telegram.supports_drafts = True
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        dm = await adapter.open_live_text("555")
        assert isinstance(dm, TelegramDraftLiveText)
        await dm.update("dm progress")
        await dm.close("dm final")
        dm_sends = list(fake_telegram.calls_for("sendMessage"))

        group = await adapter.open_live_text("-100123", chat_kind="group", thread_id="8")
        assert isinstance(group, TelegramLiveText)
        await group.update("group progress")
        await group.update("group progress, further")
        await group.close("group final")
    finally:
        await adapter.stop()

    drafts = fake_telegram.calls_for("sendMessageDraft")
    assert [d["text"] for d in drafts] == ["dm progress"]
    assert all(str(d["chat_id"]) == "555" for d in drafts)
    # The DM had no status message to create or delete.
    assert dm_sends == []
    # The group used the edited status message: sent, then deleted on close.
    group_sends = [s for s in fake_telegram.calls_for("sendMessage") if s["chat_id"] == "-100123"]
    assert [s["text"] for s in group_sends] == ["group progress"]
    assert group_sends[0]["message_thread_id"] == 8
    # The next snapshot rewrote THAT message in place: the fake numbers sends
    # from 101 and the DM sent none, so the status message is message 101.
    edits = fake_telegram.calls_for("editMessageText")
    assert [(e["chat_id"], e["message_id"], e["text"]) for e in edits] == [
        ("-100123", "101", "group progress, further")
    ]
    deletes = fake_telegram.calls_for("deleteMessage")
    assert [(d["chat_id"], d["message_id"]) for d in deletes] == [("-100123", "101")]


@pytest.mark.acceptance(
    spec="channels/telegram",
    scenario="a selection card becomes an inline keyboard with a bold title line",
)
async def test_a_selection_card_is_an_inline_keyboard_under_a_bold_title(
    fake_telegram: FakeTelegram,
) -> None:
    # A real /model card over a catalogue that includes one id too long for the
    # callback budget and enough entries to paginate.
    picks = [f"model-{i}" for i in range(9)] + ["x" * 80]
    card = model_card(current="model-1", picks=picks)
    adapter = make_telegram_adapter(fake_telegram)
    try:
        await adapter.send_text("555", card.text, buttons=card.buttons, title=card.title)
    finally:
        await adapter.stop()
    [sent] = fake_telegram.calls_for("sendMessage")
    assert sent["text"].startswith(f"<b>{card.title}</b>\n")
    keyboard = sent["reply_markup"]["inline_keyboard"]
    buttons = [b for row in keyboard for b in row]
    assert [b["text"] for b in buttons] == [b.label for b in card.buttons]
    assert all(len(b["callback_data"].encode("utf-8")) <= 64 for b in buttons)
    assert any(b["callback_data"].startswith("page:model:") for b in buttons)
