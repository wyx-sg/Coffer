"""Acceptance tests for the parent `channels` requirements about platform
surfaces — capability probing, the per-chat streaming surface, and button
vocabulary — exercised against the Telegram adapter and its in-process fake
Bot API, the one transport that implements all three.
"""

from __future__ import annotations

import pytest

from coffer.application.channel.selection_cards import model_card

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
    spec="channels", scenario="the option in effect is shown disabled on a selection card"
)
async def test_the_current_choice_is_sent_as_a_disabled_button(
    fake_telegram: FakeTelegram,
) -> None:
    card = model_card(
        current="opus", picks=["opus", "sonnet"], labels={"opus": "Opus", "sonnet": "Sonnet"}
    )
    adapter = make_telegram_adapter(fake_telegram)
    await adapter.start(RecordingCallbacks().as_callbacks())
    try:
        await adapter.send_text("555", card.text, buttons=card.buttons, title=card.title)
    finally:
        await adapter.stop()

    rows = fake_telegram.calls_for("sendMessage")[0]["reply_markup"]["inline_keyboard"]
    buttons = {b["callback_data"]: b for row in rows for b in row}
    chosen, other = buttons["model:opus"], buttons["model:sonnet"]
    assert "disabled" in chosen  # the platform's disabled state
    assert chosen["text"] == "✓ Opus"  # marked as the current choice
    assert "disabled" not in other and "style" not in other
    assert other["text"] == "Sonnet"
