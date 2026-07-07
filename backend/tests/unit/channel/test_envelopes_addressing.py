"""Tests for addressing and thread fields in InboundMessage and ChannelCapabilities."""

from datetime import UTC, datetime

from coffer.domain.channel.envelopes import InboundMessage

UTC = UTC


def _msg(**kw):
    """Build a minimal InboundMessage with defaults and apply overrides."""
    defaults = {
        "channel": "test-channel",
        "chat_id": "chat123",
        "sender_display": "Test User",
        "text": "test message",
        "platform_message_id": "msg456",
        "timestamp": datetime.now(tz=UTC),
    }
    defaults.update(kw)
    return InboundMessage(**defaults)


def test_new_addressing_fields_default_backward_compatible():
    """InboundMessage addressing fields default to backward-compatible values."""
    m = _msg()
    assert (m.chat_kind, m.addressed, m.thread_id) == ("direct", True, "")


def test_group_thread_message_fields():
    """InboundMessage can be configured as group/thread with addressing."""
    m = _msg(chat_kind="group", addressed=True, thread_id="t1")
    assert m.thread_id == "t1" and m.chat_kind == "group"
