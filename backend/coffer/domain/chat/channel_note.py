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
    #: The owner's rewrite of the reply style for this chat kind (spec channels
    #: "Let the owner rewrite a channel's reply style"); "" when they have not
    #: rewritten it or the chat kind is unknown, and Coffer's default applies.
    #: It never touches the channel note above it.
    reply_style: str = ""
    #: The transport can read a thread's earlier messages, so the agent is told
    #: the tool that does (``coffer__channel_read_thread``).
    reads_threads: bool = False
    #: A group where others than the owners may ask (spec channels "Let others
    #: in a group ask the bot"), so the agent is told what such a turn allows.
    others_can_ask: bool = False
