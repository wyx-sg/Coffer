"""SeaTalkAdapter against an in-process fake Open API (no real network).

Covers app_access_token caching + refresh-on-code-100, 429 backoff, the
single_chat text/interactive_message payloads, and handle_event
normalization of subscriber messages and approval clicks.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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


# -- interactive selection cards (P3) -----------------------------------------


async def test_send_text_with_buttons_emits_interactive_card(fake_seatalk: FakeSeaTalk) -> None:
    from coffer.domain.channel.envelopes import ChoiceButton

    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_text(
            "emp-1",
            "Pick a model:",
            buttons=[ChoiceButton(label="opus", value="model:opus")],
        )
    finally:
        await adapter.stop()
    [(body, _auth)] = fake_seatalk.single_chat_calls
    message = body["message"]
    assert message["tag"] == "interactive_message"
    assert message["interactive_message"]["buttons"] == [
        {"button_type": "callback", "text": "opus", "value": "model:opus"}
    ]


# -- group / thread send (Task 4) --------------------------------------------


async def test_send_text_group_posts_group_chat_with_thread_id(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        sent = await adapter.send_text("gid-1", "hi", chat_kind="group", thread_id="t1")
    finally:
        await adapter.stop()
    assert fake_seatalk.single_chat_calls == []  # group send never hits single_chat
    [(body, _auth)] = fake_seatalk.group_chat_calls
    assert body == {
        "group_id": "gid-1",
        "message": {"tag": "text", "text": {"format": 1, "content": "hi"}},
        "thread_id": "t1",
    }
    assert sent.message_id == "m1"


async def test_send_text_group_without_thread_id_omits_thread_field(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_text("gid-1", "hi", chat_kind="group")
    finally:
        await adapter.stop()
    [(body, _auth)] = fake_seatalk.group_chat_calls
    assert "thread_id" not in body


async def test_send_text_direct_still_uses_single_chat(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_text("emp-1", "hi")
    finally:
        await adapter.stop()
    assert fake_seatalk.group_chat_calls == []
    [(body, _auth)] = fake_seatalk.single_chat_calls
    assert body["employee_code"] == "emp-1"


async def test_capabilities_declare_groups_and_history_fetch(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        assert adapter.capabilities.supports_groups is True
        assert adapter.capabilities.supports_history_fetch is True
    finally:
        await adapter.stop()


async def test_interactive_message_click_routes_to_on_callback(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "interactive_message_click",
                "timestamp": 1718000000,
                "event": {
                    "employee_code": "emp-1",
                    "value": "agent:codex",
                    "message_id": "card-9",
                },
            }
        )
    finally:
        await adapter.stop()
    [cb] = recorder.callbacks
    assert (cb.channel, cb.chat_id, cb.sender_id, cb.data) == (
        "st",
        "emp-1",
        "emp-1",
        "agent:codex",
    )
    assert cb.platform_message_id == "card-9"


# -- context fetch (Task 5) ---------------------------------------------------


def _text_message(email: str, plain_text: str) -> dict:
    return {"sender": {"email": email}, "tag": "text", "text": {"plain_text": plain_text}}


async def test_fetch_thread_maps_thread_page_to_forwarded_items(fake_seatalk: FakeSeaTalk) -> None:
    fake_seatalk.thread_response = {
        "code": 0,
        "thread_messages": [
            _text_message("alice@example.com", "in the thread"),
            _text_message("bob@example.com", "replying"),
        ],
    }
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        items = await adapter.fetch_thread("gid-1", "t1", limit=50)
    finally:
        await adapter.stop()
    assert [(it.sender, it.text) for it in items] == [
        ("alice@example.com", "in the thread"),
        ("bob@example.com", "replying"),
    ]
    [params] = fake_seatalk.thread_calls
    assert params == {"group_id": "gid-1", "thread_id": "t1", "page_size": "50"}


async def test_message_to_item_maps_non_text_tags() -> None:
    from coffer.infrastructure.channel.seatalk import _message_to_item

    image_item = _message_to_item(
        {"sender": {"email": "a@x.com"}, "tag": "image", "image": {"content": "img-key-1"}}
    )
    assert (image_item.sender, image_item.text) == ("a@x.com", "[image] img-key-1")

    file_item = _message_to_item(
        {"sender": {"email": "a@x.com"}, "tag": "file", "file": {"filename": "report.pdf"}}
    )
    assert (file_item.sender, file_item.text) == ("a@x.com", "[file] report.pdf")

    forwarded_item = _message_to_item(
        {"sender": {"email": "a@x.com"}, "tag": "combined_forwarded_chat_history"}
    )
    assert (forwarded_item.sender, forwarded_item.text) == (
        "a@x.com",
        "[forwarded chat record]",
    )

    other_item = _message_to_item({"sender": {}, "tag": "sticker"})
    assert (other_item.sender, other_item.text) == ("unknown", "[sticker]")

    # single-chat text uses "content" instead of group's "plain_text"
    single_chat_item = _message_to_item(
        {"sender": {"email": "a@x.com"}, "tag": "text", "text": {"content": "hi"}}
    )
    assert single_chat_item.text == "hi"


async def test_fetch_thread_degrades_to_empty_list_on_error(
    fake_seatalk: FakeSeaTalk, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any transport/parse/permission error must never break a group turn —
    fetch_thread degrades to no fetched context."""
    adapter = make_seatalk_adapter(fake_seatalk)

    async def _boom(*args: object, **kwargs: object) -> Any:
        raise ChannelSendFailed("st", "group_chat/get_thread_by_thread_id: code=103 http=200")

    monkeypatch.setattr(adapter, "_get", _boom)
    try:
        assert await adapter.fetch_thread("gid-1", "t1", limit=50) == []
    finally:
        await adapter.stop()
