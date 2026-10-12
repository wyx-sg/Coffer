"""What a channel's System prompt section shows (spec channels "Let the owner
rewrite a channel's reply style"): per chat kind, Coffer's fixed channel note as
this channel sends it, Coffer's default reply style, and whether the owner's
rewrite was written against an older default.

The text comes from the same functions a turn is composed from
(``coffer.domain.chat.channel_prompt``), so what the page shows is what the
agent gets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from coffer.domain.chat.channel_prompt import (
    channel_note_text,
    default_reply_style,
    reply_style_hash,
)

if TYPE_CHECKING:
    from coffer.application.channel.prompt_note import ChannelNoteReader
    from coffer.domain.channel.config import ChannelConfig

_READER: ChannelNoteReader | None = None


def set_channel_prompt_reader(reader: ChannelNoteReader | None) -> None:
    global _READER
    _READER = reader


class ChannelPromptOut(BaseModel):
    """One chat kind's system prompt, as the page shows it."""

    #: Coffer's fixed channel note for this chat kind on this channel: read-only.
    channel_note: str
    #: Coffer's current default reply style — what applies while the owner has
    #: not rewritten it, and what "Restore default" puts back.
    default_style: str
    #: The owner rewrote the style against a default that has changed since.
    default_changed: bool


class ChannelPromptsOut(BaseModel):
    direct: ChannelPromptOut
    group: ChannelPromptOut


async def channel_prompts(uid: str, settings: ChannelConfig | None) -> ChannelPromptsOut | None:
    """``None`` before the channel kind is wired, or for a stored configuration
    that no longer validates."""
    if _READER is None or settings is None:
        return None
    notes = await _READER.preview(uid)

    def one(kind: str) -> ChannelPromptOut:
        default = default_reply_style(kind)
        style = getattr(settings, f"{kind}_reply_style")
        base = getattr(settings, f"{kind}_reply_style_base")
        return ChannelPromptOut(
            channel_note=channel_note_text(notes[kind]),
            default_style=default,
            default_changed=bool(style) and base != reply_style_hash(default),
        )

    return ChannelPromptsOut(direct=one("direct"), group=one("group"))
