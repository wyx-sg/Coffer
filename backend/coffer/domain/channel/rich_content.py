"""Pure helpers that flatten rich inbound content (forwarded records, fetched
thread/recent history, quoted replies) and the message's own provenance into
readable text folded into a turn prompt. No platform schema — adapters map their
payloads to these shapes first."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from coffer.domain.channel.envelopes import InboundMessage

__all__ = [
    "ForwardedItem",
    "flatten_context",
    "flatten_forwarded",
    "format_origin",
    "quote_prefix",
]


@dataclass(frozen=True)
class ForwardedItem:
    sender: str
    text: str  # rendered body: text, or "[image] <url>" / "[file] <name>"


def _render(items: Sequence[ForwardedItem], title: str) -> str:
    if not items:
        return ""
    lines = [f"[{title}]"]
    lines += [f"{it.sender or 'unknown'}: {it.text}" for it in items]
    return "\n".join(lines)


def flatten_forwarded(
    items: Sequence[ForwardedItem], *, title: str = "Forwarded chat record"
) -> str:
    return _render(items, title)


def flatten_context(items: Sequence[ForwardedItem], *, title: str) -> str:
    return _render(items, title)


def quote_prefix(sender: str, text: str) -> str:
    return f"> {sender or 'unknown'}: {text}\n"


#: A group title is chat-member-settable, so it is clipped before it reaches the
#: prompt — long enough to stay recognizable, short enough not to crowd the turn.
_DISPLAY_MAX = 120


def _one_line(value: str) -> str:
    """Collapse an untrusted display string onto one safe line.

    A group title (and a sender's display name) is set by people in the chat, so
    it arrives as untrusted text that is about to be folded into an agent prompt.
    A newline would let a rename forge extra ``key: value`` lines inside the
    origin block, and a quote would let it close the title early; neither
    survives here.
    """
    cleaned = " ".join("".join(" " if ch < " " or ch == '"' else ch for ch in value).split())
    return cleaned[:_DISPLAY_MAX].rstrip()


def format_origin(msg: InboundMessage, *, platform: str) -> str:
    """Render a turn's own provenance as a context block (FR-042).

    The agent otherwise sees only the message text and cannot tell which group,
    thread, or platform it is answering in — "which group is this?" becomes a
    guess, and a platform tool call has no chat id to aim at. ``platform`` is the
    binding's channel type (the envelope carries the Coffer resource name, not
    the platform). Lines with nothing to say are omitted rather than rendered
    empty.
    """
    title = _one_line(msg.chat_title)
    chat = f'{msg.chat_kind} "{title}"' if title else msg.chat_kind
    lines = [
        "[Message origin]",
        f"platform: {platform}",
        f"chat: {chat} (id: {msg.chat_id})",
    ]
    if msg.thread_id:
        lines.append(f"thread: {msg.thread_id}")
    sender = _one_line(msg.sender_display)
    if sender:
        lines.append(f"from: {sender}")
    return "\n".join(lines)
