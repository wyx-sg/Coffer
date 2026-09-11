"""Rewriting a delivered Telegram selection card.

A helper module beside ``telegram.py``, like ``telegram_media.py``: the adapter
keeps the port method, the wire call lives here so that file stays inside the
size cap.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from coffer.domain.channel.envelopes import ChoiceButton
from coffer.infrastructure.channel.render import markdown_to_telegram_html
from coffer.infrastructure.channel.telegram_media import inline_keyboard


async def edit_card(
    call: Callable[..., Awaitable[Any]],
    chat_id: str,
    message_id: str,
    markdown: str,
    buttons: Sequence[ChoiceButton],
    *,
    title: str = "",
) -> None:
    """Rewrite a card's text and its buttons in one ``editMessageText``.

    A Telegram "card" is an ordinary message carrying an inline keyboard, so one
    call covers both halves — and sending the keyboard again matters as much as
    the text: omit ``reply_markup`` and the stale buttons stay live, which is
    exactly the problem an in-place rewrite exists to fix.

    Telegram has no card title element, so the title becomes a bold first line —
    the same information in the platform's own shape.
    """
    body = f"**{title}**\n{markdown}" if title else markdown
    await call(
        "editMessageText",
        chat_id=chat_id,
        message_id=int(message_id),
        text=markdown_to_telegram_html(body),
        parse_mode="HTML",
        reply_markup=inline_keyboard(buttons),
    )
