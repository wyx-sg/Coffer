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


@dataclass(frozen=True)
class ApprovalClick:
    """A tap on an approval prompt button."""

    channel: str
    chat_id: str
    value: str  # opaque payload the core encoded into the button
    prompt_message_id: str


@dataclass(frozen=True)
class ChannelCapabilities:
    """What a transport can do; the core picks strategies from this."""

    supports_edit: bool  # progress streaming via message edits
    supports_buttons: bool  # interactive approval prompts
    supports_typing: bool  # typing indicator ack
    max_message_chars: int  # outbound chunk budget


@dataclass(frozen=True)
class SentMessage:
    """Handle to a delivered platform message (for later edit/delete)."""

    message_id: str


def encode_approval_value(request_id: str, decision: str) -> str:
    """Encode an approval button payload (single owner of the wire format)."""
    return f"{request_id}|{decision}"


def parse_approval_value(value: str) -> tuple[str, str] | None:
    """Decode a button payload back to ``(request_id, decision)``.

    Returns None for anything that is not a well-formed approval payload.
    """
    request_id, sep, decision = value.rpartition("|")
    if not sep or not request_id or decision not in ("allow", "deny"):
        return None
    return request_id, decision
