"""Pure helpers for the provenance and the other people's messages a channel turn
carries: the ``[Message origin]`` block, and :class:`ForwardedItem`, the one shape
every forwarded record, thread message and quote is mapped to before
:mod:`turn_content` renders it. No platform schema — adapters map their payloads
to these shapes first."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from coffer.domain.turn_markers import ORIGIN, ORIGIN_END, block, when

if TYPE_CHECKING:  # envelopes names ForwardedItem at runtime
    from coffer.domain.channel.envelopes import InboundMessage

__all__ = [
    "ForwardedItem",
    "format_origin",
    "one_line",
    "unavailable",
]

#: The media a model cannot read, by the platform's message type.
_UNREADABLE = {"voice": "audio", "audio": "audio", "video": "video"}


def unavailable(tag: str) -> str:
    """What a line says in place of a message the turn cannot carry —
    ``[voice] unavailable — the model cannot read audio`` — rather than a bare
    ``[voice]`` that reads as if something were there to look at."""
    what = _UNREADABLE.get(tag)
    if what:
        return f"[{tag}] unavailable — the model cannot read {what}"
    return f"[{tag}] unavailable — this message type is not passed to the model"


@dataclass(frozen=True)
class ForwardedItem:
    """One message of someone else's, as a line of the turn text."""

    sender: str
    #: The rendered body: text, or ``[image] <url>`` / ``[file] <name>`` /
    #: ``[voice] unavailable — …`` — what the line says when its media did not
    #: reach the turn.
    text: str
    #: The platform's stable id of the sender, where it supplies one; a sender
    #: whose id is the asker's is marked ``(owner)``.
    sender_id: str = ""
    #: The transport's key for the media this item carries ("" for none) — the
    #: same key its downloaded ``InboundAttachment.ref`` carries, so the line can
    #: point at ``→ attachment #n`` instead of a link the agent cannot open.
    media_ref: str = ""
    #: What the line says in place of ``text`` once that media was downloaded:
    #: ``[image]``, ``[file] report.pdf``, ``[voice]``.
    media_label: str = ""
    #: When it was sent, where the platform's payload says so.
    sent_at: datetime | None = None


#: A group title is chat-member-settable, so it is clipped before it reaches the
#: prompt — long enough to stay recognizable, short enough not to crowd the turn.
_DISPLAY_MAX = 120


def one_line(value: str) -> str:
    """Collapse an untrusted display string onto one safe line.

    A group title (and a sender's display name) is set by people in the chat, so
    it arrives as untrusted text that is about to be folded into an agent prompt.
    A newline would let a rename forge extra ``key: value`` lines inside the
    origin block, and a quote would let it close the title early; neither
    survives here.
    """
    cleaned = " ".join("".join(" " if ch < " " or ch == '"' else ch for ch in value).split())
    return cleaned[:_DISPLAY_MAX].rstrip()


def _channel_line(name: str, uid: str) -> str:
    shown = one_line(name)
    if not uid:
        return f"channel: {shown}"
    return f'channel: "{shown}" (id: {uid})' if shown else f"channel: (id: {uid})"


def format_origin(
    msg: InboundMessage, *, platform: str, channel: str = "", channel_id: str = ""
) -> str:
    """Render a turn's own provenance as a context block.

    Spec channels "Open every turn with its message origin".

    The agent otherwise sees only the message text and cannot tell which group,
    thread, or platform it is answering in — "which group is this?" becomes a
    guess, and a platform tool call has no chat id to aim at. ``platform`` is the
    binding's channel type (the envelope carries the Coffer resource name, not
    the platform). ``channel`` is the channel's name, which a person chose and
    may change, and ``channel_id`` its uid, which a Coffer tool call that reads
    the chat takes (``coffer__channel_read_thread``): one platform can carry
    several channels. Lines with nothing to say are omitted rather than
    rendered empty.
    """
    title = one_line(msg.chat_title)
    chat = f'{msg.chat_kind} "{title}"' if title else msg.chat_kind
    lines = [
        f"platform: {platform}",
        *([_channel_line(channel, channel_id)] if channel or channel_id else []),
        f"chat: {chat} (id: {msg.chat_id})",
    ]
    if msg.thread_id:
        lines.append(f"thread: {msg.thread_id}")
    # Without this line "接着上面那条说" points at nothing the agent can see — the
    # quote is a platform-side link the message text never spells out. The body
    # is folded into the turn separately; if that lookup failed, this id is the
    # only trace of what was quoted.
    if msg.quoted_message_id:
        lines.append(f"quoted message: {msg.quoted_message_id}")
    # The display name is what a human recognises; the sender id (SeaTalk
    # employee_code, Telegram from.id) is what a platform tool call takes and is
    # the identity that does not change under a rename. In a DM the id happens to
    # equal chat_id, but in a group chat_id is the GROUP's — without this line the
    # sender's own id appears nowhere at all.
    sender = one_line(msg.sender_display)
    sender_id = one_line(msg.sender_id)
    # When the platform says the message was sent; omitted when it says nothing.
    sent = when(msg.timestamp)
    sent_part = [f"sent: {sent}"] if sent else []
    if sender or sender_id:
        who = sender or "unknown"
        frm = f"from: {who} (id: {sender_id})" if sender_id else f"from: {who}"
        lines.append(" · ".join([frm, *sent_part]))
    else:
        lines.extend(sent_part)
    return block(ORIGIN, ORIGIN_END, lines)
