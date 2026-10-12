"""Which of a channel's two reply styles a conversation reads (spec channels
"Let the owner rewrite a channel's reply style")."""

from __future__ import annotations

import pytest

from coffer.application.channel.prompt_note import reply_style

_CONFIG = {
    "channel_type": "telegram",
    "bot_token_ref": "channel/tg/bot-token",
    "direct_reply_style": " Answer in Chinese. ",
    "group_reply_style": "Be brief.",
}


@pytest.mark.acceptance(spec="channels", scenario="each chat kind reads its own reply style")
def test_a_chat_kind_picks_its_own_style() -> None:
    # A thread carries its chat's kind, so a direct-chat thread reads the
    # direct style and a group thread the group one.
    assert reply_style(_CONFIG, "direct") == "Answer in Chinese."
    assert reply_style(_CONFIG, "group") == "Be brief."


def test_a_channel_stored_before_the_style_reads_its_migrated_prompt() -> None:
    old = {k: v for k, v in _CONFIG.items() if "reply_style" not in k}
    style = reply_style({**old, "direct_system_prompt": "Answer in Chinese."}, "direct")
    assert style.endswith("\n\nAnswer in Chinese.")


@pytest.mark.parametrize(
    ("config", "chat_kind"),
    [
        (_CONFIG, ""),  # the conversation's chat could not be found: guess nothing
        (_CONFIG, "channel"),
        ({**_CONFIG, "direct_reply_style": ""}, "direct"),
        ({"channel_type": "telegram"}, "direct"),  # no longer validates
    ],
)
def test_an_unknown_kind_or_no_rewrite_reads_as_none(
    config: dict[str, object], chat_kind: str
) -> None:
    assert reply_style(config, chat_kind) == ""
