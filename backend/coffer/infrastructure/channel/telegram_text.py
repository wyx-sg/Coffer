"""Telegram text lengths, measured the way the Bot API measures them.

Telegram counts a message's length (the 4096 cap on ``sendMessage`` /
``editMessageText``) in UTF-16 code units, not Python code points: an astral
character such as most emoji is one code point but two units. A clip on
``len()`` therefore lets an emoji-heavy text through at up to twice the cap,
and Telegram refuses it.
"""

from __future__ import annotations

_MARKER = "…"  # one BMP code point = one UTF-16 unit


def utf16_len(text: str) -> int:
    """``text``'s length in UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def clip_tail_utf16(text: str, limit: int) -> str:
    """Keep the TAIL of ``text`` behind a leading ellipsis so the result is at
    most ``limit`` UTF-16 units; never splits a surrogate pair."""
    if utf16_len(text) <= limit:
        return text
    keep = limit - utf16_len(_MARKER)
    units = text.encode("utf-16-le")[-2 * keep :] if keep > 0 else b""
    if units and 0xDC00 <= int.from_bytes(units[:2], "little") <= 0xDFFF:
        units = units[2:]  # a low surrogate whose high half was cut off
    return _MARKER + units.decode("utf-16-le")


__all__ = ["clip_tail_utf16", "utf16_len"]
