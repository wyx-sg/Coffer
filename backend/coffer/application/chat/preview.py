"""The one-line preview of a conversation's latest message (spec chat "Show
every conversation on the Conversations page").

A turn a channel drove opens with its context blocks — ``[Message origin]``
and the like, each a paragraph whose first line is a bracketed title — ahead of
what the person wrote. The preview is the person's words, so those leading
blocks are dropped; the last paragraph always stays, so a message that is
nothing but such a block still previews as itself.
"""

from __future__ import annotations

import re

from coffer.domain.chat.message import Message, TextBlock

__all__ = ["PREVIEW_MAX_CHARS", "message_preview"]

#: Long enough to read as a sentence in a list row, short enough for one line.
PREVIEW_MAX_CHARS = 160

_CONTEXT_TITLE = re.compile(r"\[[^\]\n]+\]")


def _drop_context_blocks(text: str) -> str:
    paragraphs = text.strip().split("\n\n")
    while len(paragraphs) > 1 and _CONTEXT_TITLE.fullmatch(paragraphs[0].split("\n", 1)[0]):
        paragraphs.pop(0)
    return "\n\n".join(paragraphs)


def message_preview(message: Message) -> str | None:
    """The message's text on one line, clipped with an ellipsis; ``None`` when
    it carries no text (a tool-only turn)."""
    text = "\n\n".join(b.text for b in message.content if isinstance(b, TextBlock))
    line = " ".join(_drop_context_blocks(text).split())
    if not line:
        return None
    if len(line) > PREVIEW_MAX_CHARS:
        return line[: PREVIEW_MAX_CHARS - 1].rstrip() + "…"
    return line
