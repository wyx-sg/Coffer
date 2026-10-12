"""The system prompt a channel-driven turn carries, in its two parts (spec
channels "Tell a channel-driven agent it is on a chat channel" and "Let the
owner rewrite a channel's reply style"; ADR
channel-prompt-fixed-note-and-editable-style).

- The **channel note** is how the channel works: where the agent is, what
  renders there, how a file is sent, how to ask the owner, what it cannot click.
  Coffer keeps it; the owner sees it but cannot edit it, because a wrong word
  here breaks a feature (a file never sent, a question never asked).
- The **reply style** is how a reply should read: outcome first, short, no
  narration, evidence kept. Coffer ships a default; the owner may rewrite it
  per chat kind, and an untouched one follows Coffer's default as it changes.

Pure text: the chat adapters compose a turn from it, and the Channels page shows
the same text, so what the owner reads is what the agent gets.
"""

from __future__ import annotations

import hashlib

from coffer.domain.chat.channel_note import ChannelNote

__all__ = [
    "DEFAULT_REPLY_STYLE",
    "REPLY_STYLE_HEADING",
    "channel_note_text",
    "channel_prompt",
    "default_reply_style",
    "reply_style_hash",
]

#: Coffer's reply style for a phone chat. The same for both chat kinds today;
#: :func:`default_reply_style` is the one place that would split them.
DEFAULT_REPLY_STYLE = (
    "Do not narrate your steps; Coffer already shows that you are working. The "
    "first line is the outcome in one sentence (it becomes the notification); "
    "then at most about 15 lines. Keep code blocks under 30 lines and attach "
    "longer logs or diffs as a file. Draw a diagram or chart as a PNG file and "
    "attach it, never as diagram source. Short never means dropping evidence: "
    "quote the few log lines, errors and IDs that prove a finding verbatim, in "
    "code blocks."
)

#: The line that sets the reply style apart from the channel note above it.
REPLY_STYLE_HEADING = "Reply style:"


def default_reply_style(chat_kind: str) -> str:
    """Coffer's reply style for ``chat_kind`` (``direct`` | ``group`` | "")."""
    del chat_kind  # one style for both kinds, for now
    return DEFAULT_REPLY_STYLE


def reply_style_hash(text: str) -> str:
    """A short fingerprint of a default reply style. A rewritten style stores the
    fingerprint of the default it was written against, so the page can say when
    Coffer's default has changed since."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _where(note: ChannelNote | None) -> str:
    """``a SeaTalk group thread`` / ``a Telegram direct chat`` / ``a chat channel``."""
    if note is None:
        return "a chat channel"
    kind = {"direct": "direct chat", "group": "group chat"}.get(note.chat_kind, "chat")
    if note.in_thread:
        kind = "group thread" if note.chat_kind == "group" else "thread"
    platform = f"{note.platform} " if note.platform else ""
    named = f" (the {note.name} channel)" if note.name else ""
    article = "an" if (platform or kind)[:1].lower() in "aeiou" else "a"
    return f"{article} {platform}{kind}{named}"


def channel_note_text(note: ChannelNote | None) -> str:
    """The fixed half: where the agent is and how this channel works.

    ``note`` can be ``None`` (the channel was deleted while a thread still pointed
    at it) or thin (not running, so what renders is unknown). It then says less,
    and every instruction that holds regardless stays.
    """
    renders = f" {note.renders}" if note is not None and note.renders else ""
    # Only a transport that collapses a details section is told to write one;
    # elsewhere the section would arrive as ordinary text, so it buys nothing.
    details = (
        " Put anything long under a `## Details` heading, which Coffer collapses."
        if note is not None and note.collapses_details
        else ""
    )
    threads = (
        " Earlier thread messages: read them with `coffer__channel_read_thread` "
        "(ids from [Message origin])."
        if note is not None and note.reads_threads
        else ""
    )
    return (
        f"You are replying in {_where(note)}, most likely on the user's phone. Only "
        "what you write after your last tool call is sent, so write the whole answer "
        f"there.{details}{renders} If you need the person to confirm or choose "
        "before you continue, call `coffer__ask`: the question reaches them in this "
        "chat as buttons and their answer comes back to you. You cannot click "
        "permission or confirmation dialogs on the user's computer; if something "
        "needs one, say so and do what you can. To send a file or image, put "
        "`MEDIA:/absolute/path` (optionally `| a caption`) on its own line; the "
        "channel uploads that existing file and removes the line — nothing else you "
        f"write is sent as a file.{threads}"
    )


def channel_prompt(note: ChannelNote | None) -> str:
    """The whole channel append: the note, then the reply style in force — the
    owner's rewrite for this chat kind, or Coffer's default when there is none."""
    style = (note.reply_style.strip() if note is not None else "") or default_reply_style(
        note.chat_kind if note is not None else ""
    )
    return f"{channel_note_text(note)}\n\n{REPLY_STYLE_HEADING}\n{style}"
