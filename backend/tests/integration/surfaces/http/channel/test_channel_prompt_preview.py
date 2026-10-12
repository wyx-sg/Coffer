"""What a channel's System prompt section shows (spec channels "Let the owner
rewrite a channel's reply style")."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from coffer.domain.channel.config import parse_channel_config
from coffer.domain.chat.channel_note import ChannelNote
from coffer.domain.chat.channel_prompt import DEFAULT_REPLY_STYLE, channel_note_text
from coffer.surfaces.http.channel_prompt_preview import channel_prompts, set_channel_prompt_reader

_TG = {"channel_type": "telegram", "bot_token_ref": "channel/tg/bot"}


class _Reader:
    async def preview(self, uid: str) -> dict[str, ChannelNote]:
        return {
            kind: ChannelNote(name="tg", platform="Telegram", chat_kind=kind)
            for kind in ("direct", "group")
        }


@pytest.fixture
def reader() -> Iterator[None]:
    set_channel_prompt_reader(_Reader())  # type: ignore[arg-type]
    yield
    set_channel_prompt_reader(None)


@pytest.mark.acceptance(
    spec="channels", scenario="the Settings tab says when Coffer's default style has changed"
)
async def test_a_rewrite_against_an_older_default_is_flagged(reader: None) -> None:
    config: dict[str, Any] = {
        **_TG,
        "direct_reply_style": "Be brief.",
        "direct_reply_style_base": "0123456789ab",  # an older default
        "group_reply_style": "Be terse.",  # written against today's
    }

    prompts = await channel_prompts("uid", parse_channel_config(config))

    assert prompts is not None
    assert prompts.direct.default_changed is True
    assert prompts.group.default_changed is False
    assert prompts.direct.default_style == DEFAULT_REPLY_STYLE
    assert prompts.direct.channel_note == channel_note_text(
        ChannelNote(name="tg", platform="Telegram", chat_kind="direct")
    )


async def test_an_untouched_style_is_never_flagged(reader: None) -> None:
    prompts = await channel_prompts("uid", parse_channel_config(dict(_TG)))
    assert prompts is not None
    assert not prompts.direct.default_changed and not prompts.group.default_changed


async def test_nothing_is_shown_for_a_config_that_no_longer_validates(reader: None) -> None:
    assert await channel_prompts("uid", None) is None
