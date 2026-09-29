"""Telegram group answers open with a real mention of the asker (spec
channels/telegram "Mention the asker by name in a group answer")."""

from __future__ import annotations

import pytest

from coffer.application.channel.turn_text import mention_prefix, with_mention
from coffer.infrastructure.channel.render import markdown_to_telegram_html
from coffer.infrastructure.channel.telegram_parse import build_inbound_message
from coffer.infrastructure.channel.telegram_text import TELEGRAM_MENTION_TEMPLATE


def _group_message() -> dict[str, object]:
    return {
        "message_id": 5,
        "date": 0,
        "chat": {"id": -100, "type": "supergroup", "title": "Ops"},
        "from": {"id": 4242, "first_name": "Alex"},
        "text": "@coffer_bot is PR 441 red?",
        "entities": [{"type": "mention", "offset": 0, "length": 11}],
    }


def test_the_asker_is_addressed_by_their_telegram_id() -> None:
    built = build_inbound_message(
        _group_message(), (), channel="tg", bot_id=1, bot_username="coffer_bot"
    )
    assert built.sender_mention_id == "4242"
    assert built.sender_display == "Alex"


@pytest.mark.acceptance(
    spec="channels/telegram", scenario="a group answer mentions the asker by name"
)
def test_a_group_answer_opens_with_an_inline_mention_that_renders_as_one() -> None:
    body = with_mention(
        "PR #441 is red on one flaky e2e.",
        chat_kind="group",
        id_template=TELEGRAM_MENTION_TEMPLATE,
        user_id="4242",
        user_name="Alex",
    )
    assert body == "[Alex](tg://user?id=4242) PR #441 is red on one flaky e2e."
    # The HTML fallback renders the same thing as a mention link.
    assert markdown_to_telegram_html(body).startswith('<a href="tg://user?id=4242">Alex</a>')


def test_a_direct_answer_carries_no_mention() -> None:
    body = with_mention(
        "hi", chat_kind="direct", id_template=TELEGRAM_MENTION_TEMPLATE, user_id="4242"
    )
    assert body == "hi"


def test_a_name_cannot_break_out_of_the_link_text() -> None:
    prefix = mention_prefix(TELEGRAM_MENTION_TEMPLATE, "4242", user_name="Al](x) [ex*")
    assert prefix == "[Alx ex](tg://user?id=4242)"
    assert mention_prefix(TELEGRAM_MENTION_TEMPLATE, "4242") == "[you](tg://user?id=4242)"
