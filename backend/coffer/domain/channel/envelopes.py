"""Normalized message envelopes — the only shapes the channel core sees.

Adapters translate platform payloads (Telegram updates, SeaTalk events) to
and from these; nothing above the adapter layer knows a platform schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class InboundAttachment:
    """A file (photo/document/voice) the transport downloaded for an inbound message.

    The bytes are already saved to a local path; the core converts this to a
    chat-domain ``Attachment`` when driving the turn. Modality-neutral so a new
    media type is a new ``mime``, not a new envelope.
    """

    path: str  # absolute local path the transport downloaded the bytes to
    mime: str  # e.g. "image/jpeg", "application/pdf", "audio/ogg"
    filename: str  # best-effort original / synthesized name


@dataclass(frozen=True)
class InboundMessage:
    """A message arriving from an IM chat — text and/or downloaded attachments."""

    channel: str  # channel resource name
    chat_id: str  # Telegram chat id / SeaTalk employee_code
    sender_display: str  # best-effort human name at the platform
    text: str
    platform_message_id: str
    timestamp: datetime
    sender_id: str = ""  # stable per-sender id for the owner gate (Telegram
    # from.id, SeaTalk employee_code); "" when the transport has none
    attachments: tuple[InboundAttachment, ...] = ()  # photos/files/voice, if any


@dataclass(frozen=True)
class ChannelCapabilities:
    """What a transport can do; the core picks strategies from this."""

    supports_edit: bool  # progress streaming via message edits
    supports_typing: bool  # typing indicator ack
    max_message_chars: int  # outbound chunk budget
    supports_buttons: bool = False  # interactive selection cards (ADR-014)
    supports_media: bool = False  # outbound file/photo upload (send_media)


@dataclass(frozen=True)
class ChoiceButton:
    """One tappable option on an interactive selection card.

    ``value`` is the opaque callback payload echoed back when the owner taps
    (e.g. ``"agent:claude_code"`` / ``"model:claude-opus-4-8"``); it must stay
    small (Telegram caps callback_data at 64 bytes).
    """

    label: str  # human text shown on the button
    value: str  # callback payload routed back through InboundCallback.data


@dataclass(frozen=True)
class InboundCallback:
    """A selection-card button tap arriving from an IM chat.

    The button counterpart of ``InboundMessage``: it carries the opaque
    ``data`` (the tapped ``ChoiceButton.value``) rather than free text. The core
    owner-gates it exactly like a message before honoring the switch.
    """

    channel: str  # channel resource name
    chat_id: str  # return address (Telegram chat id / SeaTalk employee_code)
    sender_id: str  # stable per-sender id for the owner gate ("" when none)
    data: str  # the tapped ChoiceButton.value
    callback_id: str = ""  # platform ack handle (Telegram callback_query.id); "" if none
    platform_message_id: str = ""  # the card message (for an optional in-place ack)


@dataclass(frozen=True)
class SentMessage:
    """Handle to a delivered platform message (for later edit/delete)."""

    message_id: str
