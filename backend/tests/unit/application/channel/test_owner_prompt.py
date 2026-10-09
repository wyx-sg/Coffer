"""Which of a channel's two system prompts a conversation reads (spec channels
"Append the owner's system prompt to a channel turn")."""

from __future__ import annotations

import pytest

from coffer.application.channel.prompt_note import owner_prompt

_CONFIG = {"direct_system_prompt": " Answer in Chinese. ", "group_system_prompt": "Be brief."}


@pytest.mark.acceptance(spec="channels", scenario="each chat kind reads its own system prompt")
def test_a_chat_kind_picks_its_own_prompt() -> None:
    # A thread carries its chat's kind, so a direct-chat thread reads the
    # direct prompt and a group thread the group one.
    assert owner_prompt(_CONFIG, "direct") == "Answer in Chinese."
    assert owner_prompt(_CONFIG, "group") == "Be brief."


@pytest.mark.parametrize(
    ("config", "chat_kind"),
    [
        (_CONFIG, ""),  # the conversation's chat could not be found: guess nothing
        (_CONFIG, "channel"),
        ({}, "direct"),
        ({"group_system_prompt": None}, "group"),
        ({"direct_system_prompt": 42}, "direct"),
    ],
)
def test_an_unknown_kind_or_a_missing_prompt_reads_as_none(
    config: dict[str, object], chat_kind: str
) -> None:
    assert owner_prompt(config, chat_kind) == ""
