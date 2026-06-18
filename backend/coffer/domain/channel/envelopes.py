"""Normalized message envelopes — the only shapes the channel core sees.

Adapters translate platform payloads (Telegram updates, SeaTalk events) to
and from these; nothing above the adapter layer knows a platform schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class InboundMessage:
    """A text message arriving from an IM chat."""

    channel: str  # channel resource name
    chat_id: str  # Telegram chat id / SeaTalk employee_code
    sender_display: str  # best-effort human name at the platform
    text: str
    platform_message_id: str
    timestamp: datetime
    sender_id: str = ""  # stable per-sender id for the owner gate (Telegram
    # from.id, SeaTalk employee_code); "" when the transport has none


@dataclass(frozen=True)
class ChannelCapabilities:
    """What a transport can do; the core picks strategies from this."""

    supports_edit: bool  # progress streaming via message edits
    supports_typing: bool  # typing indicator ack
    max_message_chars: int  # outbound chunk budget


@dataclass(frozen=True)
class SentMessage:
    """Handle to a delivered platform message (for later edit/delete)."""

    message_id: str
