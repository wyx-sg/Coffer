"""Telegram: only allowed reactions, and scaffolding that does not ring.

Two platform facts from the Bot API docs (read 2026-09-30, Bot API 10.3):
``setMessageReaction`` takes only the fixed ``ReactionTypeEmoji`` list, and
``disable_notification`` sends a message silently. A status message the
renderer deletes, and every continuation after a reply's first piece, are sent
silently so a group is not buzzed for scaffolding.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.infrastructure.channel.live_text import TelegramLiveText
from coffer.infrastructure.channel.telegram_features import Feature
from coffer.infrastructure.channel.telegram_reactions import ALLOWED_REACTIONS, set_reaction
from coffer.infrastructure.channel.telegram_send import send_text_chunks


class _Api:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, method: str, **params: Any) -> dict[str, Any]:
        self.calls.append((method, params))
        return {"message_id": len(self.calls)}

    def sends(self) -> list[dict[str, Any]]:
        return [p for m, p in self.calls if m in ("sendMessage", "sendRichMessage")]


def test_every_reaction_coffer_sets_is_on_telegrams_list() -> None:
    for emoji in ("👀", "👨‍💻", "👌", "😢", "🤷"):
        assert emoji in ALLOWED_REACTIONS
    assert len(ALLOWED_REACTIONS) == 73


def test_the_marks_telegram_refuses_are_not_on_the_list() -> None:
    for emoji in ("✅", "❌", "⏳"):
        assert emoji not in ALLOWED_REACTIONS


async def test_a_reaction_off_the_list_is_refused_before_any_call() -> None:
    api = _Api()
    with pytest.raises(ValueError):
        await set_reaction(api, "1", "2", "✅")
    assert api.calls == []
    await set_reaction(api, "1", "2", "👌")
    assert api.calls == [
        (
            "setMessageReaction",
            {"chat_id": "1", "message_id": "2", "reaction": [{"type": "emoji", "emoji": "👌"}]},
        )
    ]


async def test_the_group_status_message_is_sent_silently() -> None:
    api = _Api()
    live = TelegramLiveText(api, "-100")
    await live.update("⏳ Bash · list the desktop")
    method, params = api.calls[0]
    assert method == "sendMessage"
    assert params["disable_notification"] is True


async def test_only_the_first_plain_chunk_notifies() -> None:
    api = _Api()
    text = "\n\n".join(["x" * 30] * 3)
    await send_text_chunks(api, "1", text, limit=40)
    sends = api.sends()
    assert len(sends) == 3
    assert "disable_notification" not in sends[0]
    assert all(s["disable_notification"] is True for s in sends[1:])


async def test_only_the_first_rich_piece_notifies() -> None:
    api = _Api()
    text = "\n\n".join(["y" * 20000, "z" * 20000])
    await send_text_chunks(api, "1", text, limit=4000, rich=Feature("rich_messages"))
    sends = api.sends()
    assert len(sends) == 2
    assert "disable_notification" not in sends[0]
    assert sends[1]["disable_notification"] is True
