"""SeaTalkAdapter against an in-process fake Open API (no real network).

Covers app_access_token caching + refresh-on-code-100, 429 backoff, the
single_chat text/interactive_message payloads, and handle_event
normalization of subscriber messages and approval clicks.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.channel.errors import ChannelSendFailed

from .conftest import FakeSeaTalk, RecordingCallbacks, make_seatalk_adapter

# -- outbound -----------------------------------------------------------------


async def test_send_text_uses_format1_and_caches_token_across_sends(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        first = await adapter.send_text("emp-1", "hello")
        second = await adapter.send_text("emp-1", "again")
    finally:
        await adapter.stop()
    assert fake_seatalk.token_calls == 1  # one grant serves both sends
    assert (first.message_id, second.message_id) == ("m1", "m2")
    bodies = [body for body, _ in fake_seatalk.single_chat_calls]
    assert bodies[0]["employee_code"] == "emp-1"
    assert bodies[0]["message"] == {"tag": "text", "text": {"format": 1, "content": "hello"}}
    auths = [auth for _, auth in fake_seatalk.single_chat_calls]
    assert auths == ["Bearer tok-1", "Bearer tok-1"]


async def test_expired_token_code_100_refreshes_and_retries(fake_seatalk: FakeSeaTalk) -> None:
    fake_seatalk.scripted = [(200, {"code": 100, "message": "token expired"})]
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        sent = await adapter.send_text("emp-1", "hi")
    finally:
        await adapter.stop()
    assert sent.message_id == "m1"
    assert fake_seatalk.token_calls == 2  # rejected token dropped, fresh one fetched
    auths = [auth for _, auth in fake_seatalk.single_chat_calls]
    assert auths == ["Bearer tok-1", "Bearer tok-2"]


async def test_rate_limited_send_backs_off_once_then_succeeds(fake_seatalk: FakeSeaTalk) -> None:
    fake_seatalk.scripted = [(429, {"code": 101})]  # exactly one 429 → one 1s backoff
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        sent = await adapter.send_text("emp-1", "hi")
    finally:
        await adapter.stop()
    assert sent.message_id == "m1"
    assert len(fake_seatalk.single_chat_calls) == 2
    assert fake_seatalk.token_calls == 1  # backoff retry reuses the cached token


async def test_platform_error_raises_channel_send_failed(fake_seatalk: FakeSeaTalk) -> None:
    fake_seatalk.scripted = [(200, {"code": 5, "message": "nope"})]
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        with pytest.raises(ChannelSendFailed):
            await adapter.send_text("emp-1", "hi")
    finally:
        await adapter.stop()
    assert len(fake_seatalk.single_chat_calls) == 1  # non-retryable: no retry


async def test_non_json_upstream_surfaces_as_channel_send_failed(
    fake_seatalk: FakeSeaTalk,
) -> None:
    # A gateway 502 returns an HTML page, not the Open API JSON envelope. The
    # raw json() would raise JSONDecodeError (NOT an httpx.HTTPError), escaping
    # the ChannelSendFailed contract; the adapter must translate it.
    fake_seatalk.html_error_sends = 1
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        with pytest.raises(ChannelSendFailed):
            await adapter.send_text("emp-1", "hi")
    finally:
        await adapter.stop()


async def test_approval_prompt_sends_interactive_card_with_callback_buttons(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        sent = await adapter.send_approval_prompt(
            "emp-1", "Run the tool?", allow_value="allow:7", deny_value="deny:7"
        )
    finally:
        await adapter.stop()
    assert sent.message_id == "m1"
    body, _auth = fake_seatalk.single_chat_calls[0]
    message = body["message"]
    assert message["tag"] == "interactive_message"
    elements = message["interactive_message"]["elements"]
    descriptions = [e for e in elements if e["element_type"] == "description"]
    assert descriptions[0]["description"]["text"] == "Run the tool?"
    buttons = [e["button"] for e in elements if e["element_type"] == "button"]
    assert [(b["button_type"], b["value"]) for b in buttons] == [
        ("callback", "allow:7"),
        ("callback", "deny:7"),
    ]


async def test_edit_and_delete_are_unsupported_capabilities(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        assert adapter.capabilities.supports_edit is False
        with pytest.raises(ChannelSendFailed):
            await adapter.edit_text("emp-1", "m1", "new")
        with pytest.raises(ChannelSendFailed):
            await adapter.delete_message("emp-1", "m1")
    finally:
        await adapter.stop()
    assert fake_seatalk.single_chat_calls == []  # nothing reached the platform


async def test_resolve_approval_prompt_sends_follow_up_text(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.resolve_approval_prompt("emp-1", "m5", "Approved")
    finally:
        await adapter.stop()
    body, _auth = fake_seatalk.single_chat_calls[0]  # no edit API → follow-up message
    assert body["message"] == {"tag": "text", "text": {"format": 1, "content": "Approved"}}


async def test_send_typing_posts_typing_endpoint(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_typing("emp-1")
    finally:
        await adapter.stop()
    assert fake_seatalk.typing_calls == [{"employee_code": "emp-1"}]


# -- inbound (events fed by the daemon's ingest route) --------------------------


async def test_handle_event_normalizes_subscriber_text_message(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "message_from_bot_subscriber",
                "timestamp": 1718000000,
                "event": {
                    "employee_code": "emp-1",
                    "email": "yu@example.com",
                    "message": {
                        "tag": "text",
                        "message_id": "pm-1",
                        "text": {"content": "hi bot"},
                    },
                },
            }
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert (msg.channel, msg.chat_id, msg.text) == ("st", "emp-1", "hi bot")
    assert msg.sender_display == "yu@example.com"
    assert msg.sender_id == "emp-1"  # 1:1 DM: sender is the employee_code
    assert msg.platform_message_id == "pm-1"
    assert msg.timestamp == datetime.fromtimestamp(1718000000, tz=UTC)
    assert recorder.clicks == []


async def test_handle_event_image_message_yields_empty_text(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "message_from_bot_subscriber",
                "timestamp": 1718000000,
                "event": {
                    "employee_code": "emp-1",
                    "message": {"tag": "image", "message_id": "pm-2", "image": {"key": "k"}},
                },
            }
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert msg.text == ""  # non-text content degrades to an empty-text envelope
    assert msg.platform_message_id == "pm-2"


async def test_handle_event_click_normalizes_approval(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "interactive_message_click",
                "timestamp": 1718000001,
                "event": {"employee_code": "emp-1", "value": "allow:7", "message_id": "pm-9"},
            }
        )
    finally:
        await adapter.stop()
    [click] = recorder.clicks
    assert (click.channel, click.chat_id, click.value) == ("st", "emp-1", "allow:7")
    assert click.prompt_message_id == "pm-9"
    assert recorder.messages == []
