"""Acceptance tests for the parent `channels` requirements about platform
surfaces — capability probing, the per-chat streaming surface, and button
vocabulary — exercised against the Telegram adapter and its in-process fake
Bot API, the one transport that implements all three.
"""

from __future__ import annotations

import pytest

from coffer.application.channel.selection_cards import agent_card
from coffer.infrastructure.channel import live_text
from coffer.infrastructure.channel.live_text import TelegramLiveText
from coffer.infrastructure.channel.telegram_draft import TelegramDraftLiveText

from .conftest import FakeTelegram, RecordingCallbacks, make_telegram_adapter


@pytest.mark.acceptance(
    spec="channels",
    scenario="a capability the platform rejects is latched off and the reply still arrives",
)
async def test_a_rejected_capability_latches_off_and_delivery_continues(
    fake_telegram: FakeTelegram,
) -> None:
    # The fake Bot API predates rich messages: it refuses sendRichMessage as an
    # unknown method, which is the platform's own "unsupported" answer.
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text("555", "## First\n\n- one")
        await adapter.send_text("555", "## Second\n\n- two")
    finally:
        await adapter.stop()

    sends = fake_telegram.calls_for("sendMessage")
    # Both replies were delivered, through the fallback mechanism.
    assert [("First" in s["text"], "Second" in s["text"]) for s in sends] == [
        (True, False),
        (False, True),
    ]
    # The newer capability was attempted exactly once, for the first reply only.
    assert len(fake_telegram.calls_for("sendRichMessage")) == 1


@pytest.mark.acceptance(
    spec="channels",
    scenario="a chat without the platform streaming surface keeps its old live mechanism",
)
async def test_the_streaming_surface_is_used_only_in_the_chats_that_have_it(
    fake_telegram: FakeTelegram, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No throttle, so the group's second snapshot is written as an edit now
    # rather than dropped for arriving inside the 1.5 s window.
    monkeypatch.setattr(live_text, "TELEGRAM_UPDATE_INTERVAL", 0.0)
    fake_telegram.supports_drafts = True  # drafts exist, for private chats only
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        direct = await adapter.open_live_text("555")
        assert isinstance(direct, TelegramDraftLiveText)
        await direct.update("thinking in the DM")
        drafts_after_dm = len(fake_telegram.calls_for("sendMessageDraft"))

        group = await adapter.open_live_text("-100123", chat_kind="group", thread_id="8")
        assert isinstance(group, TelegramLiveText)
        await group.update("thinking in the group")
        await group.update("thinking in the group, still")
    finally:
        await adapter.stop()

    drafts = fake_telegram.calls_for("sendMessageDraft")
    assert [d["text"] for d in drafts] == ["thinking in the DM"]
    assert drafts_after_dm == 1  # the group added no streaming-surface call
    # The group's progress used the edited status message instead: one status
    # message sent, then rewritten in place with the next snapshot. The fake
    # numbers sends from 101 and the DM sent none, so that message is message 101.
    sends = fake_telegram.calls_for("sendMessage")
    assert [(s["chat_id"], s["text"]) for s in sends] == [("-100123", "thinking in the group")]
    edits = fake_telegram.calls_for("editMessageText")
    assert [(e["chat_id"], e["message_id"], e["text"]) for e in edits] == [
        ("-100123", "101", "thinking in the group, still")
    ]


@pytest.mark.acceptance(
    spec="channels", scenario="the option in effect is shown disabled on a selection card"
)
async def test_the_current_choice_is_sent_as_a_disabled_button(
    fake_telegram: FakeTelegram,
) -> None:
    card = agent_card(current="codex", choices=[("codex", "Codex"), ("claude_code", "Claude Code")])
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text("555", card.text, buttons=card.buttons, title=card.title)
    finally:
        await adapter.stop()

    rows = fake_telegram.calls_for("sendMessage")[0]["reply_markup"]["inline_keyboard"]
    buttons = {b["callback_data"]: b for row in rows for b in row}
    chosen, other = buttons["agent:codex"], buttons["agent:claude_code"]
    assert "disabled" in chosen  # the platform's disabled state
    assert chosen["text"] == "Codex ✓"  # marked as the current choice
    assert "disabled" not in other and "style" not in other
    assert other["text"] == "Claude Code"
