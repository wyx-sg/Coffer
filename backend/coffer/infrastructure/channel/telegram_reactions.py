"""The emoji a Telegram bot may react with.

``setMessageReaction`` accepts only the fixed list under ``ReactionTypeEmoji``
in the Bot API docs (73 emoji, read 2026-09-30, Bot API 10.3). Anything else —
✅, ❌ and ⏳ among them — is refused, and a refusal at the call site is
suppressed as best-effort, so an emoji outside the list fails invisibly: the
✅ completion reaction never landed on any turn for exactly that reason.

The adapter therefore checks the list itself and raises before the round trip,
and a unit test pins the emoji Coffer uses to it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from coffer.domain.channel.envelopes import ReactionSet

__all__ = ["ALLOWED_REACTIONS", "TELEGRAM_REACTIONS", "set_reaction"]

ALLOWED_REACTIONS: frozenset[str] = frozenset(
    {
        "❤",
        "👍",
        "👎",
        "🔥",
        "🥰",
        "👏",
        "😁",
        "🤔",
        "🤯",
        "😱",
        "🤬",
        "😢",
        "🎉",
        "🤩",
        "🤮",
        "💩",
        "🙏",
        "👌",
        "🕊",
        "🤡",
        "🥱",
        "🥴",
        "😍",
        "🐳",
        "❤\u200d🔥",
        "🌚",
        "🌭",
        "💯",
        "🤣",
        "⚡",
        "🍌",
        "🏆",
        "💔",
        "🤨",
        "😐",
        "🍓",
        "🍾",
        "💋",
        "🖕",
        "😈",
        "😴",
        "😭",
        "🤓",
        "👻",
        "👨\u200d💻",
        "👀",
        "🎃",
        "🙈",
        "😇",
        "😨",
        "🤝",
        "✍",
        "🤗",
        "🫡",
        "🎅",
        "🎄",
        "☃",
        "💅",
        "🤪",
        "🗿",
        "🆒",
        "💘",
        "🙉",
        "🦄",
        "😘",
        "💊",
        "🙊",
        "😎",
        "👾",
        "🤷\u200d♂",
        "🤷",
        "🤷\u200d♀",
        "😡",
    }
)


#: 👀 received → 👨‍💻 working → 👌 done / 😢 failed / 🤷 stopped — all on the list
#: above (a unit test pins it).
TELEGRAM_REACTIONS = ReactionSet(
    received="👀", working="👨‍💻", done="👌", failed="😢", stopped="🤷"
)


async def set_reaction(
    call: Callable[..., Awaitable[Any]], chat_id: str, message_id: str, emoji: str
) -> None:
    """React on ``message_id`` with ``emoji`` — which must be on the list.

    A bot holds one reaction per message, so a new one replaces the last: the
    user's message shows the turn's current state, never a pile of them.
    """
    if emoji not in ALLOWED_REACTIONS:
        raise ValueError(f"{emoji!r} is not a reaction Telegram allows a bot to set")
    reaction = [{"type": "emoji", "emoji": emoji}]
    await call("setMessageReaction", chat_id=chat_id, message_id=message_id, reaction=reaction)
