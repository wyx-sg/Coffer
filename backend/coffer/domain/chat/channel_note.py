"""What a channel-driven agent is told about where it is (spec channels "Tell a
channel-driven agent it is on a chat channel").

Shared by both kinds: the channel kind builds it from its own state and the
transport's declared capabilities, and chat's prompt composer reads it — chat
never imports channel code, so the value that crosses the seam lives here.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ChannelNote"]


@dataclass(frozen=True)
class ChannelNote:
    """The facts the channel note is written from. Every field may be empty —
    a deleted channel, a conversation no chat can be found for — and the note
    then says less, never something untrue."""

    #: The channel's current name, as the owner calls it.
    name: str = ""
    #: The platform's own name ("SeaTalk", "Telegram").
    platform: str = ""
    #: ``direct`` | ``group`` | "" when unknown.
    chat_kind: str = ""
    #: The conversation lives in a thread (a group thread, a Telegram topic).
    in_thread: bool = False
    #: One or two sentences on the Markdown that renders there, declared by the
    #: transport (``ChannelCapabilities.render_notes``); "" when it is not running.
    renders: str = ""
    #: The transport collapses a ``## Details`` section itself
    #: (``ChannelCapabilities.collapses_details``), so the agent may use one.
    collapses_details: bool = False
    #: The owner's own system prompt for this chat kind — the channel's direct-chat
    #: or group-chat prompt (spec channels "Append the owner's system prompt to a
    #: channel turn"); "" when none is set or the chat kind is unknown. It is
    #: appended after the note, never in its place.
    owner_prompt: str = ""
