"""Normalized envelopes: frozen value semantics the channel core relies on."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime

import pytest

from coffer.domain.channel.envelopes import (
    ChannelCapabilities,
    InboundMessage,
    SentMessage,
)


def _inbound(**overrides: object) -> InboundMessage:
    base: dict = {
        "channel": "tg-main",
        "chat_id": "42",
        "sender_display": "Ada",
        "text": "hello",
        "platform_message_id": "m1",
        "timestamp": datetime(2026, 6, 12, tzinfo=UTC),
    }
    base.update(overrides)
    return InboundMessage(**base)


def test_inbound_message_is_frozen():
    msg = _inbound()
    with pytest.raises(FrozenInstanceError):
        msg.text = "tampered"  # type: ignore[misc]


def test_inbound_message_value_equality():
    assert _inbound() == _inbound()
    assert _inbound(text="other") != _inbound()


def test_channel_capabilities_carries_strategy_fields():
    caps = ChannelCapabilities(supports_edit=True, supports_typing=True, max_message_chars=4096)
    assert (caps.supports_edit, caps.supports_typing) == (True, True)
    assert caps.max_message_chars == 4096
    assert {f.name for f in fields(ChannelCapabilities)} == {
        "supports_edit",
        "supports_typing",
        "max_message_chars",
    }


def test_sent_message_is_frozen_handle():
    sent = SentMessage(message_id="m9")
    assert sent == SentMessage(message_id="m9")
    with pytest.raises(FrozenInstanceError):
        sent.message_id = "m10"  # type: ignore[misc]
