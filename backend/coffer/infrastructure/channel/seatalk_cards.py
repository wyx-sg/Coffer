"""Rewriting a delivered SeaTalk interactive card.

A helper module beside ``seatalk.py``, like ``seatalk_media.py`` and
``seatalk_parse.py``: the adapter keeps the port method, the wire call lives
here so that file stays inside the size cap.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from coffer.domain.channel.envelopes import ChoiceButton
from coffer.infrastructure.channel.render import markdown_to_seatalk
from coffer.infrastructure.channel.seatalk_parse import interactive_card


async def update_interactive_card(
    post: Callable[[str, dict[str, Any]], Awaitable[Any]],
    message_id: str,
    markdown: str,
    buttons: Sequence[ChoiceButton],
    *,
    title: str = "",
) -> None:
    """Rewrite a delivered card through SeaTalk's Update Message.

    Applies to interactive cards ONLY — never to a text message, which is why
    ``supports_edit`` stays false while ``supports_card_update`` is true — and
    only within 7 days, only for the bot that sent it. All three hold for a
    selection card Coffer just sent and the owner just tapped.

    The card is rebuilt rather than patched: the platform replaces the whole
    message, and rebuilding from the current state is what keeps the tick
    honest.
    """
    await post(
        "/messaging/v2/update",
        {
            "message_id": message_id,
            "message": interactive_card(markdown_to_seatalk(markdown), buttons, title=title),
        },
    )
