"""SeaTalkAdapter against an in-process fake Open API (no real network).

Covers app_access_token caching + refresh-on-code-100, 429 backoff, the
single_chat text/interactive_message payloads, and handle_event
normalization of subscriber messages and approval clicks.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.envelopes import InboundLifecycle
from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel.live_text import SeaTalkLiveText
from coffer.infrastructure.channel.seatalk_send import (
    SEATALK_MENTION_EMAIL_TEMPLATE,
    SEATALK_MENTION_TEMPLATE,
)

from .conftest import FakeSeaTalk, RecordingCallbacks, make_seatalk_adapter, wait_until


class LifecycleRecorder(RecordingCallbacks):
    """``RecordingCallbacks`` plus the ``on_lifecycle`` hook. Kept here rather
    than in the shared conftest because SeaTalk is the only adapter that emits
    standing changes so far."""

    def __init__(self) -> None:
        super().__init__()
        self.lifecycle: list[InboundLifecycle] = []

    async def on_lifecycle(self, event: InboundLifecycle) -> None:
        self.lifecycle.append(event)

    def as_callbacks(self) -> AdapterCallbacks:
        return AdapterCallbacks(
            on_message=self.on_message,
            on_callback=self.on_callback,
            on_lifecycle=self.on_lifecycle,
        )


def _route_dm_thread(fake: FakeSeaTalk) -> list[dict[str, Any]]:
    """Same for the single-chat thread read (SeaTalk app v3.62.1+), so a DM
    thread fetch is distinguishable from the group one the fake already serves."""
    calls: list[dict[str, Any]] = []

    async def handler(request: Request) -> JSONResponse:
        calls.append(dict(request.query_params))
        return JSONResponse(content={"code": 0, "thread_messages": []})

    fake.app.get("/messaging/v2/single_chat/get_thread_by_thread_id")(handler)
    return calls


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
        await adapter.send_typing("emp-1")  # chat_kind defaults to "direct"
    finally:
        await adapter.stop()
    assert fake_seatalk.typing_calls == [{"employee_code": "emp-1"}]
    assert fake_seatalk.group_typing_calls == []


async def test_send_typing_in_a_group_thread_uses_the_group_endpoint(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """A group has its own typing endpoint, and it takes the thread — so the
    cue appears where the reply will, not in the group's main channel."""
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_typing("gid-1", thread_id="t1", chat_kind="group")
    finally:
        await adapter.stop()
    assert fake_seatalk.group_typing_calls == [{"group_id": "gid-1", "thread_id": "t1"}]
    assert fake_seatalk.typing_calls == []  # never the DM endpoint


async def test_send_typing_in_a_group_without_a_thread_omits_it(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """An @mention outside a thread types in the group's main channel. thread_id
    is optional there, and sending an empty one would name no thread at all."""
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_typing("gid-1", chat_kind="group")
    finally:
        await adapter.stop()
    assert fake_seatalk.group_typing_calls == [{"group_id": "gid-1"}]


async def test_typing_in_a_too_large_group_is_a_silent_no_op(fake_seatalk: FakeSeaTalk) -> None:
    """Code 7003 ("Group chat too large") means the group has more than 200
    members and typing can NEVER be triggered there — a permanent property of
    that group, not a transient fault. It must not raise and must not retry."""
    fake_seatalk.group_typing_code = 7003
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_typing("gid-1", chat_kind="group")
    finally:
        await adapter.stop()
    # Attempted once: a ~4s indicator is not worth a retry, and this one can
    # never succeed however often it is asked for.
    assert fake_seatalk.group_typing_calls == [{"group_id": "gid-1"}]


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


async def test_handle_event_dm_surfaces_the_quoted_message_id(fake_seatalk: FakeSeaTalk) -> None:
    """A reply that quotes an earlier message carries only the quoted id. The
    adapter hands that id to the turn and stops there — resolving the quoted
    BODY is get_message_by_message_id, an agent-invoked lookup, not transport."""
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
                        "message_id": "pm-2",
                        "quoted_message_id": "pm-1",
                        "text": {"content": "about this"},
                    },
                },
            }
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert msg.quoted_message_id == "pm-1"
    assert msg.platform_message_id == "pm-2"  # the quote is not the message itself


async def test_handle_event_without_a_quote_leaves_the_id_empty(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            _subscriber_text_envelope(event_id="ev-1", message_id="pm-1", text="hi")
        )
        await adapter.handle_event(_group_mention_envelope(plain_text="@Bot hi", username="Bot"))
    finally:
        await adapter.stop()
    assert [m.quoted_message_id for m in recorder.messages] == ["", ""]


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
    assert msg.attachments == ()  # no image.content URL → nothing to download


def test_collect_image_urls_direct_and_nested_forwarded() -> None:
    from coffer.infrastructure.channel.seatalk_media import collect_image_urls

    direct = {"tag": "image", "image": {"content": "https://o.io/file/a"}}
    assert collect_image_urls(direct) == ["https://o.io/file/a"]

    # A forwarded record wraps the leaves a level deeper; images are collected
    # recursively, text/other entries ignored.
    forwarded = {
        "tag": "combined_forwarded_chat_history",
        "combined_forwarded_chat_history": {
            "content": [
                {
                    "tag": "combined_forwarded_chat_history",
                    "combined_forwarded_chat_history": {
                        "content": [
                            {"tag": "text", "text": {"content": "hi"}},
                            {"tag": "image", "image": {"content": "https://o.io/file/b?seq=1"}},
                            {"tag": "image", "image": {"content": "https://o.io/file/c?seq=2"}},
                        ]
                    },
                }
            ]
        },
    }
    assert collect_image_urls(forwarded) == [
        "https://o.io/file/b?seq=1",
        "https://o.io/file/c?seq=2",
    ]
    assert collect_image_urls({"tag": "text", "text": {"content": "x"}}) == []


def test_collect_media_covers_image_file_generic_and_forwarded() -> None:
    """FR-028: the media collector returns a downloadable ref for an image, a
    directly-sent file (with its filename + a non-image mime), and — best
    effort — any other tag whose sub-dict carries a file-URL content
    (voice/video), recursing forwarded records. A plain text message yields
    nothing."""
    from coffer.infrastructure.channel.seatalk_media import collect_media

    image = collect_media({"tag": "image", "image": {"content": "https://o.io/file/a"}})
    assert [(r.url, r.kind) for r in image] == [("https://o.io/file/a", "image")]

    # A directly-sent file: the captured live shape (message.file.content is the
    # auth-gated URL, message.file.filename the original name).
    file_refs = collect_media(
        {
            "tag": "file",
            "message_id": "m",
            "file": {"content": "https://o.io/file/b", "filename": "create_acc.sh"},
        }
    )
    [file_ref] = file_refs
    assert (file_ref.url, file_ref.filename, file_ref.kind) == (
        "https://o.io/file/b",
        "create_acc.sh",
        "file",
    )
    assert file_ref.mime is not None and not file_ref.mime.startswith("image/")

    # Generic best-effort: an unverified video tag whose sub-dict has a file URL.
    video = collect_media(
        {"tag": "video", "video": {"content": "https://o.io/file/v", "filename": "clip.mp4"}}
    )
    assert [(r.url, r.filename, r.kind) for r in video] == [
        ("https://o.io/file/v", "clip.mp4", "media")
    ]

    # A file buried in a forwarded record is collected recursively.
    forwarded = collect_media(
        {
            "tag": "combined_forwarded_chat_history",
            "combined_forwarded_chat_history": {
                "content": [
                    {
                        "tag": "combined_forwarded_chat_history",
                        "combined_forwarded_chat_history": {
                            "content": [
                                {"tag": "text", "text": {"content": "see file"}},
                                {
                                    "tag": "file",
                                    "file": {
                                        "content": "https://o.io/file/f",
                                        "filename": "notes.txt",
                                    },
                                },
                            ]
                        },
                    }
                ]
            },
        }
    )
    assert [(r.url, r.filename, r.kind) for r in forwarded] == [
        ("https://o.io/file/f", "notes.txt", "file")
    ]

    assert collect_media({"tag": "text", "text": {"content": "x"}}) == []


async def test_handle_event_direct_image_downloads_attachment(
    fake_seatalk: FakeSeaTalk, tmp_path: Any
) -> None:
    """A directly-sent image is fetched (authenticated) and attached so the
    agent can actually see it — not left as an unopenable file link."""
    adapter = make_seatalk_adapter(fake_seatalk, media_dir=tmp_path)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "message_from_bot_subscriber",
                "timestamp": 1718000000,
                "event": {
                    "employee_code": "emp-1",
                    "message": {
                        "tag": "image",
                        "message_id": "pm-img",
                        "thread_id": "",
                        "image": {"content": "https://openapi.seatalk.io/messaging/v2/file/imgabc"},
                    },
                },
            }
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert fake_seatalk.file_downloads == ["imgabc"]
    [att] = msg.attachments
    assert att.mime == "image/png"
    assert pathlib.Path(att.path).read_bytes() == fake_seatalk.file_bytes


async def test_handle_event_forwarded_record_downloads_images(
    fake_seatalk: FakeSeaTalk, tmp_path: Any
) -> None:
    """Images buried in a forwarded chat record are downloaded and attached
    (the original chart-in-a-forwarded-record report), while the text still
    flattens as before."""
    adapter = make_seatalk_adapter(fake_seatalk, media_dir=tmp_path)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "message_from_bot_subscriber",
                "timestamp": 1718000000,
                "event": {
                    "employee_code": "emp-1",
                    "message": {
                        "tag": "combined_forwarded_chat_history",
                        "message_id": "pm-f",
                        "combined_forwarded_chat_history": {
                            "content": [
                                {
                                    "tag": "combined_forwarded_chat_history",
                                    "sender": {"email": "y@x.com"},
                                    "combined_forwarded_chat_history": {
                                        "content": [
                                            {
                                                "tag": "text",
                                                "sender": {"email": "j@x.com"},
                                                "text": {"content": "see chart:"},
                                            },
                                            {
                                                "tag": "image",
                                                "sender": {"email": "j@x.com"},
                                                "image": {
                                                    "content": "https://openapi.seatalk.io/messaging/v2/file/chart1?seq=2"
                                                },
                                            },
                                        ]
                                    },
                                }
                            ]
                        },
                    },
                },
            }
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert "j@x.com: see chart:" in msg.text  # text still flattened
    assert fake_seatalk.file_downloads == ["chart1"]  # ?seq=2 is a query param
    [att] = msg.attachments
    assert att.mime == "image/png"


@pytest.mark.acceptance(spec="channels", scenario="an inbound SeaTalk file drives a turn")
async def test_handle_event_direct_file_downloads_attachment(
    fake_seatalk: FakeSeaTalk, tmp_path: Any
) -> None:
    """FR-028: a directly-sent file (not an image) is fetched (authenticated) and
    attached with its real filename + a non-image mime, so it drives a turn like
    a photo does instead of hitting the "unsupported message" branch. Uses the
    live-captured shape: ``message.file.content`` is the auth-gated URL and
    ``message.file.filename`` the original name."""
    adapter = make_seatalk_adapter(fake_seatalk, media_dir=tmp_path)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "message_from_bot_subscriber",
                "timestamp": 1718000000,
                "event": {
                    "employee_code": "emp-1",
                    "message": {
                        "tag": "file",
                        "message_id": "pm-file",
                        "thread_id": "",
                        "file": {
                            "content": "https://openapi.seatalk.io/messaging/v2/file/fileabc",
                            "filename": "create_acc.sh",
                        },
                    },
                },
            }
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert fake_seatalk.file_downloads == ["fileabc"]
    [att] = msg.attachments
    # The real filename is preserved (not a uuid) so the agent sees create_acc.sh.
    assert att.filename == "create_acc.sh"
    assert pathlib.Path(att.path).read_bytes() == fake_seatalk.file_bytes
    # A non-image mime (from the .sh extension) — never the download's image/png
    # content-type — so the file is not misread as a picture.
    assert not att.mime.startswith("image/")
    # It drives a turn: an attachment is present, so the inbound pipeline's
    # "empty envelope → Unsupported" guard (text-or-attachment) does not fire.
    assert msg.attachments != ()


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
    card = message["interactive_message"]
    # A button is an ELEMENT, not a sibling of `elements`. Emitting a `buttons`
    # array alongside them is the shape SeaTalk does not render.
    assert "buttons" not in card
    # SeaTalk renders at most 5 bare buttons per card, which a 6-agent selection
    # exceeds — buttons ship inside button_group elements (up to 3 each), the
    # buttons themselves bare rather than individually wrapped.
    assert card["elements"] == [
        {"element_type": "description", "description": {"format": 1, "text": "Pick a model:"}},
        {
            "element_type": "button_group",
            "button_group": [{"button_type": "callback", "text": "opus", "value": "model:opus"}],
        },
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
    # thread_id lives INSIDE the message body, not as a top-level sibling —
    # verified live that a top-level thread_id is ignored and the reply lands
    # in the group main chat instead of the thread.
    assert body == {
        "group_id": "gid-1",
        "message": {"tag": "text", "text": {"format": 1, "content": "hi"}, "thread_id": "t1"},
    }
    assert "thread_id" not in body  # never a top-level sibling
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
    assert "thread_id" not in body  # not a top-level sibling
    assert "thread_id" not in body["message"]  # and not in the message body


# -- outbound media (FR-031) --------------------------------------------------


async def test_send_media_image_posts_group_image_with_thread_in_body(
    fake_seatalk: FakeSeaTalk, tmp_path: Any
) -> None:
    """FR-031: a returned image during a group-thread turn is uploaded as a
    SeaTalk ``image`` message (base64 content) to group_chat, with thread_id
    INSIDE the message body so it lands in the originating thread."""
    import base64

    img = tmp_path / "chart.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nDATA")
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        assert adapter.capabilities.supports_media is True
        sent = await adapter.send_media(
            "gid-1", str(img), as_photo=True, thread_id="t1", chat_kind="group"
        )
    finally:
        await adapter.stop()
    assert fake_seatalk.single_chat_calls == []  # group upload never hits single_chat
    [(body, _auth)] = fake_seatalk.group_chat_calls
    b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nDATA").decode("ascii")
    assert body == {
        "group_id": "gid-1",
        "message": {"tag": "image", "image": {"content": b64}, "thread_id": "t1"},
    }
    assert "thread_id" not in body  # never a top-level sibling
    assert sent.message_id == "m1"


async def test_send_media_non_image_posts_file_message(
    fake_seatalk: FakeSeaTalk, tmp_path: Any
) -> None:
    """A non-image file is uploaded as a SeaTalk ``file`` message carrying the
    filename and base64 content (as_photo is ignored — SeaTalk picks the tag)."""
    import base64

    doc = tmp_path / "report.pdf"
    doc.write_bytes(b"%PDF-1.4 body")
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_media("emp-1", str(doc), as_photo=True)
    finally:
        await adapter.stop()
    assert fake_seatalk.group_chat_calls == []  # a direct upload uses single_chat
    [(body, _auth)] = fake_seatalk.single_chat_calls
    b64 = base64.b64encode(b"%PDF-1.4 body").decode("ascii")
    assert body == {
        "employee_code": "emp-1",
        "message": {"tag": "file", "file": {"filename": "report.pdf", "content": b64}},
    }
    assert "thread_id" not in body["message"]  # no thread → no thread field


async def test_send_media_caption_follows_as_threaded_text(
    fake_seatalk: FakeSeaTalk, tmp_path: Any
) -> None:
    """A caption is sent as a following short text message, threaded the same
    way (SeaTalk file/image messages carry no caption field)."""
    img = tmp_path / "chart.png"
    img.write_bytes(b"PNGDATA")
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_media(
            "gid-1", str(img), caption="here it is", thread_id="t1", chat_kind="group"
        )
    finally:
        await adapter.stop()
    bodies = [body for body, _ in fake_seatalk.group_chat_calls]
    assert len(bodies) == 2  # file first, then the caption text
    assert bodies[0]["message"]["tag"] == "image"
    assert bodies[0]["message"]["thread_id"] == "t1"
    assert bodies[1]["message"] == {
        "tag": "text",
        "text": {"format": 1, "content": "here it is"},
        "thread_id": "t1",
    }


async def test_send_text_direct_still_uses_single_chat(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_text("emp-1", "hi")
    finally:
        await adapter.stop()
    assert fake_seatalk.group_chat_calls == []
    [(body, _auth)] = fake_seatalk.single_chat_calls
    assert body["employee_code"] == "emp-1"


async def test_send_text_direct_with_thread_id_threads_the_reply(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """FR-026: a DM reply sent inside a thread must carry thread_id on the
    single_chat message body so SeaTalk threads it — documented wire
    placement, not yet live-verified against the real platform."""
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_text("emp-1", "hi", thread_id="t1")
    finally:
        await adapter.stop()
    [(body, _auth)] = fake_seatalk.single_chat_calls
    assert body["employee_code"] == "emp-1"
    assert body["message"]["thread_id"] == "t1"


async def test_send_text_direct_without_thread_id_omits_thread_field(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_text("emp-1", "hi")
    finally:
        await adapter.stop()
    [(body, _auth)] = fake_seatalk.single_chat_calls
    assert "thread_id" not in body["message"]


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
    # A DM tap carries no group_id → routes as a direct reply, no thread.
    assert cb.chat_kind == "direct"
    assert cb.thread_id == ""


async def test_interactive_message_click_in_group_routes_as_group_callback(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """FR-034: a card tapped in a GROUP arrives with a ``group_id`` (mirroring
    the group @mention event) and the tapper under ``sender`` — the adapter
    normalizes it to a group callback (chat_kind="group", chat_id=group_id,
    thread_id set, sender_id = the tapper's employee_code) so the core
    owner-gates and replies in the group thread, not a DM."""
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "interactive_message_click",
                "timestamp": 1718000000,
                "event": {
                    "group_id": "gid-1",
                    "thread_id": "t-7",
                    "sender": {"employee_code": "emp-2", "email": "sender@shopee.com"},
                    "value": "agent:codex",
                    "message_id": "card-9",
                },
            }
        )
    finally:
        await adapter.stop()
    [cb] = recorder.callbacks
    assert cb.chat_kind == "group"
    assert cb.chat_id == "gid-1"
    assert cb.thread_id == "t-7"
    assert cb.sender_id == "emp-2"
    assert cb.data == "agent:codex"
    assert cb.platform_message_id == "card-9"


# -- inbound de-duplication (FR-039) ------------------------------------------


def _subscriber_text_envelope(*, event_id: str, message_id: str, text: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": "message_from_bot_subscriber",
        "timestamp": 1718000000,
        "event": {
            "employee_code": "emp-1",
            "email": "yu@example.com",
            "message": {"tag": "text", "message_id": message_id, "text": {"content": text}},
        },
    }


@pytest.mark.acceptance(spec="channels", scenario="a redelivered event is processed once")
async def test_handle_event_dedups_redelivered_event_id(fake_seatalk: FakeSeaTalk) -> None:
    """FR-039: SeaTalk retries a slow callback, so the SAME event_id can arrive
    twice — the second delivery must be dropped, driving the turn once. Two
    DIFFERENT event_ids remain two turns."""
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        env = _subscriber_text_envelope(event_id="ev-1", message_id="pm-1", text="hi bot")
        await adapter.handle_event(env)
        await adapter.handle_event(dict(env))  # a byte-for-byte redelivery
        assert len(recorder.messages) == 1  # processed exactly once
        # A genuinely different event still drives its own turn.
        await adapter.handle_event(
            _subscriber_text_envelope(event_id="ev-2", message_id="pm-2", text="again")
        )
    finally:
        await adapter.stop()
    assert [m.text for m in recorder.messages] == ["hi bot", "again"]


async def test_handle_event_dedups_by_message_id_when_event_id_absent(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """When an envelope carries no top-level event_id, de-dup falls back to the
    message id so a redelivery is still dropped."""
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        env = {
            "event_type": "message_from_bot_subscriber",
            "timestamp": 1718000000,
            "event": {
                "employee_code": "emp-1",
                "message": {"tag": "text", "message_id": "pm-9", "text": {"content": "hi"}},
            },
        }
        await adapter.handle_event(env)
        await adapter.handle_event(dict(env))
    finally:
        await adapter.stop()
    assert len(recorder.messages) == 1


async def test_handle_event_dedups_redelivered_interactive_click(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """A redelivered card tap (same event_id) fires on_callback once, not twice
    — a double reply / double agent switch would otherwise result."""
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    click = {
        "event_id": "ev-click",
        "event_type": "interactive_message_click",
        "timestamp": 1718000000,
        "event": {"employee_code": "emp-1", "value": "agent:codex", "message_id": "card-9"},
    }
    try:
        await adapter.handle_event(click)
        await adapter.handle_event(dict(click))
    finally:
        await adapter.stop()
    assert len(recorder.callbacks) == 1


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
        items, atts = await adapter.fetch_thread("gid-1", "t1", limit=50)
    finally:
        await adapter.stop()
    assert [(it.sender, it.text) for it in items] == [
        ("alice@example.com", "in the thread"),
        ("bob@example.com", "replying"),
    ]
    assert atts == ()  # a text-only thread downloads nothing
    [params] = fake_seatalk.thread_calls
    assert params == {"group_id": "gid-1", "thread_id": "t1", "page_size": "50"}


async def test_fetch_thread_recurses_forwarded_records_in_the_thread(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """A forwarded chat record sitting IN a thread must be flattened to its
    leaf messages when the thread is read for context — not collapsed to the
    ``[forwarded chat record]`` placeholder. This is the fetch_thread analogue
    of the inbound nested-forward fix: reading a thread whose messages include
    a forwarded record (the shape SeaTalk delivers, wrapped one level deeper)
    must recurse the same way the DM/@mention path does."""
    fake_seatalk.thread_response = {
        "code": 0,
        "thread_messages": [
            _text_message("owner@example.com", "look at this"),
            {
                "tag": "combined_forwarded_chat_history",
                "sender": {"email": "owner@example.com"},
                "combined_forwarded_chat_history": {
                    "content": [
                        {
                            "tag": "text",
                            "sender": {"email": "john.phuatd@shopee.com"},
                            "text": {"content": "Do you see this issue?"},
                        },
                        {
                            "tag": "text",
                            "sender": {"email": "yuxing.wu@shopee.com"},
                            "text": {"content": "let me check"},
                        },
                    ]
                },
            },
        ],
    }
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        items, _atts = await adapter.fetch_thread("gid-1", "t1", limit=50)
    finally:
        await adapter.stop()
    rendered = [(it.sender, it.text) for it in items]
    assert ("owner@example.com", "look at this") in rendered
    assert ("john.phuatd@shopee.com", "Do you see this issue?") in rendered
    assert ("yuxing.wu@shopee.com", "let me check") in rendered
    # The placeholder must never leak into the thread context.
    assert all(it.text != "[forwarded chat record]" for it in items)


@pytest.mark.acceptance(spec="channels", scenario="thread-history images reach a vision agent")
async def test_fetch_thread_downloads_thread_images(
    fake_seatalk: FakeSeaTalk, tmp_path: Any
) -> None:
    """FR-029: when the @mention lands inside a thread, the images the thread's
    own messages carry — a directly-sent image AND one buried in a forwarded
    record — are downloaded (authenticated) and returned as the second tuple
    element, so a picture in the thread reaches the vision agent as real bytes
    instead of a dead auth-gated file link."""
    fake_seatalk.thread_response = {
        "code": 0,
        "thread_messages": [
            _text_message("owner@example.com", "look at these"),
            {
                "tag": "image",
                "sender": {"email": "owner@example.com"},
                "image": {"content": "https://openapi.seatalk.io/messaging/v2/file/direct1"},
            },
            {
                "tag": "combined_forwarded_chat_history",
                "sender": {"email": "owner@example.com"},
                "combined_forwarded_chat_history": {
                    "content": [
                        {
                            "tag": "image",
                            "sender": {"email": "j@x.com"},
                            "image": {
                                "content": "https://openapi.seatalk.io/messaging/v2/file/fwd1?seq=3"
                            },
                        },
                    ]
                },
            },
        ],
    }
    adapter = make_seatalk_adapter(fake_seatalk, media_dir=tmp_path)
    try:
        items, atts = await adapter.fetch_thread("gid-1", "t1", limit=50)
    finally:
        await adapter.stop()
    # Text still flattens (the leaf image in the forwarded record contributes no text).
    assert ("owner@example.com", "look at these") in [(it.sender, it.text) for it in items]
    # Both images downloaded — the direct one and the one nested in the forward.
    assert fake_seatalk.file_downloads == ["direct1", "fwd1"]  # ?seq=3 is a query param
    assert len(atts) == 2
    assert all(a.mime == "image/png" for a in atts)
    assert all(pathlib.Path(a.path).read_bytes() == fake_seatalk.file_bytes for a in atts)


async def testmessage_to_item_maps_non_text_tags() -> None:
    from coffer.infrastructure.channel.seatalk_parse import message_to_item

    image_item = message_to_item(
        {"sender": {"email": "a@x.com"}, "tag": "image", "image": {"content": "img-key-1"}}
    )
    assert (image_item.sender, image_item.text) == ("a@x.com", "[image] img-key-1")

    file_item = message_to_item(
        {"sender": {"email": "a@x.com"}, "tag": "file", "file": {"filename": "report.pdf"}}
    )
    assert (file_item.sender, file_item.text) == ("a@x.com", "[file] report.pdf")

    forwarded_item = message_to_item(
        {"sender": {"email": "a@x.com"}, "tag": "combined_forwarded_chat_history"}
    )
    assert (forwarded_item.sender, forwarded_item.text) == (
        "a@x.com",
        "[forwarded chat record]",
    )

    other_item = message_to_item({"sender": {}, "tag": "sticker"})
    assert (other_item.sender, other_item.text) == ("unknown", "[sticker]")

    # single-chat text uses "content" instead of group's "plain_text"
    single_chat_item = message_to_item(
        {"sender": {"email": "a@x.com"}, "tag": "text", "text": {"content": "hi"}}
    )
    assert single_chat_item.text == "hi"


async def test_handle_event_forwarded_record_flattens_into_text(fake_seatalk: FakeSeaTalk) -> None:
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
                    "email": "yuxing.wu@shopee.com",
                    "message": {
                        "tag": "combined_forwarded_chat_history",
                        "message_id": "pm-3",
                        "thread_id": "",
                        "combined_forwarded_chat_history": {
                            "content": [
                                {
                                    "tag": "text",
                                    "sender": {"email": "john.phuatd@shopee.com"},
                                    "message_sent_time": 1718000001,
                                    "text": {"content": "Do you see this issue?"},
                                },
                                {
                                    "tag": "image",
                                    "sender": {"email": "john.phuatd@shopee.com"},
                                    "message_sent_time": 1718000002,
                                    "image": {"content": "https://cdn.example.com/img.png"},
                                },
                                {
                                    "tag": "text",
                                    "sender": {"email": "yuxing.wu@shopee.com"},
                                    "message_sent_time": 1718000003,
                                    "text": {"content": "let me check"},
                                },
                            ]
                        },
                    },
                },
            }
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert msg.text.startswith("[Forwarded chat record]")
    assert "john.phuatd@shopee.com: Do you see this issue?" in msg.text
    assert "[image] https://cdn.example.com/img.png" in msg.text
    assert "yuxing.wu@shopee.com: let me check" in msg.text
    assert msg.thread_id == ""


async def test_handle_event_nested_forwarded_record_recurses(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """When a chat record is forwarded, SeaTalk wraps the real messages one
    level deeper: the top-level ``content`` holds a single entry that is
    itself ``tag == combined_forwarded_chat_history`` whose OWN
    ``combined_forwarded_chat_history.content`` carries the leaf messages.
    The flattener must recurse into that nesting instead of emitting the
    ``[forwarded chat record]`` placeholder for the whole record (the shape
    captured live in ~/.coffer daemon logs; the original bug report).
    """
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
                    "email": "yuxing.wu@shopee.com",
                    "message": {
                        "tag": "combined_forwarded_chat_history",
                        "message_id": "pm-nested",
                        "thread_id": "",
                        "combined_forwarded_chat_history": {
                            "content": [
                                {
                                    "tag": "combined_forwarded_chat_history",
                                    "sender": {"email": "yuxing.wu@shopee.com"},
                                    "message_sent_time": 1718000000,
                                    "combined_forwarded_chat_history": {
                                        "content": [
                                            {
                                                "tag": "text",
                                                "sender": {"email": "john.phuatd@shopee.com"},
                                                "message_sent_time": 1718000001,
                                                "text": {"content": "Do you see this issue?"},
                                            },
                                            {
                                                "tag": "image",
                                                "sender": {"email": "john.phuatd@shopee.com"},
                                                "message_sent_time": 1718000002,
                                                "image": {
                                                    "content": "https://cdn.example.com/i.png"
                                                },
                                            },
                                            {
                                                "tag": "text",
                                                "sender": {"email": "yuxing.wu@shopee.com"},
                                                "message_sent_time": 1718000003,
                                                "text": {"content": "let me check"},
                                            },
                                        ]
                                    },
                                },
                            ]
                        },
                    },
                },
            }
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert msg.text.startswith("[Forwarded chat record]")
    assert "john.phuatd@shopee.com: Do you see this issue?" in msg.text
    assert "[image] https://cdn.example.com/i.png" in msg.text
    assert "yuxing.wu@shopee.com: let me check" in msg.text
    # The placeholder must NOT leak through — the whole point of recursing.
    assert "[forwarded chat record]" not in msg.text


# -- group / @mention inbound (Task 6) ----------------------------------------


def _group_mention_envelope(
    *,
    plain_text: str,
    username: str,
    thread_id: str = "",
    group_id: str = "gid-1",
    quoted_message_id: str = "",
) -> dict[str, Any]:
    return {
        "event_type": "new_mentioned_message_received_from_group_chat",
        "timestamp": 1718000000,
        "event": {
            "group_id": group_id,
            "message": {
                "message_id": "gm-1",
                "thread_id": thread_id,
                "quoted_message_id": quoted_message_id,
                "sender": {
                    "seatalk_id": "st-1",
                    "employee_code": "emp-2",
                    "email": "sender@shopee.com",
                    "sender_type": 1,
                },
                "tag": "text",
                "text": {
                    "plain_text": plain_text,
                    "mentioned_list": [{"username": username, "seatalk_id": "bot-1"}],
                },
            },
        },
    }


async def test_handle_event_group_mention_in_main_chat(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            _group_mention_envelope(
                plain_text="@Yuxing's Work Assistant hi",
                username="Yuxing's Work Assistant",
            )
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert msg.chat_kind == "group"
    assert msg.chat_id == "gid-1"
    assert msg.addressed is True
    assert msg.text == "hi"
    # A main-chat @mention (incoming thread_id == "") must reply INTO the thread
    # SeaTalk roots at this @mention — never the group main chat. The thread's id
    # equals the @mention's own message_id, so that is the reply thread_id.
    assert msg.thread_id == "gm-1"
    assert msg.thread_id == msg.platform_message_id
    assert msg.sender_id == "emp-2"
    assert msg.sender_display == "sender@shopee.com"
    assert msg.platform_message_id == "gm-1"


async def test_handle_event_group_mention_in_thread_sets_thread_id(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            _group_mention_envelope(
                plain_text="@Yuxing's Work Assistant hi",
                username="Yuxing's Work Assistant",
                thread_id="t-9",
            )
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert msg.chat_kind == "group"
    assert msg.addressed is True
    assert msg.text == "hi"
    assert msg.thread_id == "t-9"


async def test_handle_event_group_mention_surfaces_the_quoted_message_id(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """Same as the DM path: an @mention quoting an earlier group message hands
    the turn the quoted id. The docs warn a message has DIFFERENT message_ids
    for different apps, so the id is only resolvable by this same bot."""
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            _group_mention_envelope(
                plain_text="@Bot what about this",
                username="Bot",
                quoted_message_id="gm-0",
            )
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert msg.quoted_message_id == "gm-0"
    assert msg.platform_message_id == "gm-1"


async def test_handle_event_group_forwarded_record_flattens_into_text(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """A group @mention whose message IS a forwarded record (tag ==
    ``combined_forwarded_chat_history``) must be flattened the same way the
    DM path flattens it — not dropped to empty text via ``plain_text``."""
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "new_mentioned_message_received_from_group_chat",
                "timestamp": 1718000000,
                "event": {
                    "group_id": "gid-1",
                    "message": {
                        "message_id": "gm-3",
                        "thread_id": "",
                        "sender": {"employee_code": "emp-2", "email": "sender@shopee.com"},
                        "tag": "combined_forwarded_chat_history",
                        "combined_forwarded_chat_history": {
                            "content": [
                                {
                                    "tag": "text",
                                    "sender": {"email": "john.phuatd@shopee.com"},
                                    "text": {"content": "Do you see this issue?"},
                                },
                                {
                                    "tag": "text",
                                    "sender": {"email": "yuxing.wu@shopee.com"},
                                    "text": {"content": "let me check"},
                                },
                            ]
                        },
                    },
                },
            }
        )
    finally:
        await adapter.stop()
    [msg] = recorder.messages
    assert msg.text.startswith("[Forwarded chat record]")
    assert "john.phuatd@shopee.com: Do you see this issue?" in msg.text
    assert "yuxing.wu@shopee.com: let me check" in msg.text
    assert msg.chat_kind == "group"
    assert msg.addressed is True
    assert msg.chat_id == "gid-1"


async def test_handle_event_ignores_non_mention_thread_messages(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "new_message_received_from_thread",
                "timestamp": 1718000000,
                "event": {
                    "group_id": "gid-1",
                    "message": {
                        "message_id": "gm-2",
                        "thread_id": "t-9",
                        "sender": {"employee_code": "emp-3", "email": "other@shopee.com"},
                        "tag": "text",
                        "text": {"plain_text": "just chatting", "mentioned_list": []},
                    },
                },
            }
        )
    finally:
        await adapter.stop()
    assert recorder.messages == []


async def test_handle_event_ignores_bot_added_to_group_chat(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "bot_added_to_group_chat",
                "timestamp": 1718000000,
                "event": {"group_id": "gid-1"},
            }
        )
    finally:
        await adapter.stop()
    assert recorder.messages == []


def _removed_envelope(*, event_id: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": "bot_removed_from_group_chat",
        "timestamp": 1718000000,
        "event": {
            "group_id": "gid-1",
            "remover": {
                "seatalk_id": "st-9",
                "employee_code": "emp-9",
                "email": "remover@shopee.com",
            },
        },
    }


def _external_envelope(*, event_id: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": "group_chat_converted_to_external_group",
        "timestamp": 1718000000,
        "event": {"group_id": "gid-1"},
    }


async def test_bot_removed_from_group_reaches_on_lifecycle(fake_seatalk: FakeSeaTalk) -> None:
    """Removal is a change in what the binding IS, not a turn: every later send
    to this group would fail, so the core has to hear about it — but nothing
    about it belongs on the message path."""
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = LifecycleRecorder()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(_removed_envelope(event_id="ev-r1"))
    finally:
        await adapter.stop()
    [event] = recorder.lifecycle
    assert (event.channel, event.chat_id, event.kind) == ("st", "gid-1", "removed_from_group")
    # The remover is named the way sender_display is everywhere else: email first.
    assert event.actor_display == "remover@shopee.com"
    assert recorder.messages == []
    assert recorder.callbacks == []


async def test_group_converted_to_external_reaches_on_lifecycle(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """People outside the organisation can read what lands here from now on.
    SeaTalk names nobody in this event, so actor_display stays empty."""
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = LifecycleRecorder()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(_external_envelope(event_id="ev-x1"))
    finally:
        await adapter.stop()
    [event] = recorder.lifecycle
    assert (event.chat_id, event.kind, event.actor_display) == (
        "gid-1",
        "group_became_external",
        "",
    )
    assert recorder.messages == []


async def test_redelivered_lifecycle_event_fires_once(fake_seatalk: FakeSeaTalk) -> None:
    """FR-039 covers these like every other event — a retried callback must not
    report the same removal twice."""
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = LifecycleRecorder()
    await adapter.start(recorder.as_callbacks())
    try:
        env = _removed_envelope(event_id="ev-r1")
        await adapter.handle_event(env)
        await adapter.handle_event(dict(env))  # a byte-for-byte redelivery
        await adapter.handle_event(_external_envelope(event_id="ev-x1"))
    finally:
        await adapter.stop()
    assert [e.kind for e in recorder.lifecycle] == ["removed_from_group", "group_became_external"]


async def test_lifecycle_events_are_dropped_without_an_on_lifecycle_hook(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """``on_lifecycle`` is optional: a consumer that never set it must not blow
    up, and the event must not leak onto the message path instead."""
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()  # as_callbacks() leaves on_lifecycle=None
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(_removed_envelope(event_id="ev-r1"))
        await adapter.handle_event(_external_envelope(event_id="ev-x1"))
    finally:
        await adapter.stop()
    assert recorder.messages == []
    assert recorder.callbacks == []


async def test_fetch_thread_in_a_dm_reads_the_single_chat_endpoint(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """Threads are no longer group-only (SeaTalk app v3.62.1+ threads DMs too),
    so chat_kind picks the read endpoint — and a DM's chat_id IS the peer's
    employee_code, which is why the same argument feeds both."""
    dm_thread = _route_dm_thread(fake_seatalk)
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        fetched = await adapter.fetch_thread("emp-1", "t1", limit=20, chat_kind="direct")
    finally:
        await adapter.stop()
    assert fetched == ([], ())
    assert dm_thread == [{"employee_code": "emp-1", "thread_id": "t1", "page_size": "20"}]
    assert fake_seatalk.thread_calls == []  # the group endpoint stayed untouched


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
        assert await adapter.fetch_thread("gid-1", "t1", limit=50) == ([], ())
    finally:
        await adapter.stop()


# -- live text: the message-streaming API (FR-037) ----------------------------


def _ticking(step: float = 1.0) -> Any:
    """A clock that advances past the surface's buffer on every read, so a test
    drives updates deterministically instead of sleeping."""
    box = [0.0]

    def now() -> float:
        value = box[0]
        box[0] += step
        return value

    return now


def _live(adapter: Any, chat_id: str = "emp-1", **kwargs: Any) -> SeaTalkLiveText:
    return SeaTalkLiveText(adapter._post, chat_id, now=_ticking(), **kwargs)


@pytest.mark.acceptance(
    spec="channels",
    scenario="each seatalk stream update carries the full reply so far",
)
async def test_stream_opens_once_and_updates_carry_full_snapshots(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    live = _live(adapter)
    try:
        await live.update("I found")
        await live.update("I found three")
        leftover = await live.close("I found three cats.")
    finally:
        await adapter.stop()

    # ONE init_stream for the whole turn, on the single-chat surface. It posts a
    # real message, so it carries one — a body with only the target is refused
    # (code=102), which is how this shipped broken.
    assert [surface for surface, _ in fake_seatalk.init_stream_calls] == ["single_chat"]
    assert fake_seatalk.init_stream_calls[0][1] == {
        "employee_code": "emp-1",
        # format 1 even for this opening snapshot: the message must be able to
        # carry an @mention the instant it is created (FR-070), and a tag in a
        # format-2 message shows as its own source. Partial text stays literal
        # because it is ESCAPED, not because the format is plain.
        "message": {"tag": "text", "text": {"format": 1, "content": "I found"}},
    }
    bodies = [body for _surface, body in fake_seatalk.update_stream_calls]
    # An update names its target too: a stream_id alone does not say which chat.
    assert all(b["employee_code"] == "emp-1" for b in bodies)
    # seq starts at 1 on the first UPDATE — init_stream consumes none…
    assert [b["seq"] for b in bodies] == [1, 2]
    assert {b["stream_id"] for b in bodies} == {"s1"}
    # …each update carries the FULL accumulated text, never a delta…
    assert [b["message"]["text"]["content"] for b in bodies] == [
        "I found three",
        "I found three cats.",
    ]
    # …an update never re-states the kind, which init_stream fixed…
    assert all("tag" not in b["message"] for b in bodies)
    # …and only the last one finishes the stream.
    assert [b["finish"] for b in bodies] == [False, True]
    assert leftover == ""  # the streamed message IS the reply


async def test_stream_updates_are_buffered_not_sent_per_token(fake_seatalk: FakeSeaTalk) -> None:
    # A frozen clock keeps every update inside the ~200 ms buffer, so only the
    # first snapshot reaches the platform — the rest are dropped, not queued.
    adapter = make_seatalk_adapter(fake_seatalk)
    live = SeaTalkLiveText(adapter._post, "emp-1", now=lambda: 5.0)
    try:
        await live.update("I")
        await live.update("I fo")
        await live.update("I found")
        await live.close("I found cats.")
    finally:
        await adapter.stop()

    # The first snapshot opens the stream (init_stream carries it); the next two
    # fall inside the buffer and are dropped, so only the finish updates.
    assert fake_seatalk.init_stream_calls[0][1]["message"]["text"]["content"] == "I"
    contents = [body["message"]["text"]["content"] for _s, body in fake_seatalk.update_stream_calls]
    assert contents == ["I found cats."]


@pytest.mark.acceptance(
    spec="channels",
    scenario="a terminated seatalk stream is never reused",
)
async def test_a_terminated_stream_is_never_reused_and_the_reply_is_handed_back(
    fake_seatalk: FakeSeaTalk,
) -> None:
    # The platform kills the stream on the 2nd update (as it does on a >30 s gap
    # or any error); every later request naming that id would be rejected.
    fake_seatalk.fail_stream_update_at = 2
    adapter = make_seatalk_adapter(fake_seatalk)
    live = _live(adapter)
    try:
        await live.update("one")
        await live.update("one two")  # rejected → the stream is dead
        await live.update("one two three")  # must not reach the platform
        leftover = await live.close("one two three.")
    finally:
        await adapter.stop()

    assert len(fake_seatalk.update_stream_calls) == 2  # nothing after the rejection
    assert len(fake_seatalk.init_stream_calls) == 1  # and no second stream either
    # The turn still owes the user a reply: the whole text comes back for the
    # ordinary send path.
    assert leftover == "one two three."


async def test_a_stream_that_never_opened_hands_the_whole_reply_back(
    fake_seatalk: FakeSeaTalk,
) -> None:
    fake_seatalk.stream_init_fails = 1
    adapter = make_seatalk_adapter(fake_seatalk)
    live = _live(adapter)
    try:
        await live.update("hello")
        leftover = await live.close("hello there")
    finally:
        await adapter.stop()

    assert fake_seatalk.update_stream_calls == []
    assert leftover == "hello there"


@pytest.mark.acceptance(
    spec="channels",
    scenario="a reply past the stream budget finishes the stream and sends the rest",
)
async def test_reply_past_the_stream_budget_finishes_at_the_limit_and_returns_the_rest(
    fake_seatalk: FakeSeaTalk,
) -> None:
    # A reply's length is unknown until it ends, so an overlong one streams up to
    # the platform's per-stream cap and hands the remainder back.
    head = "A" * 3000
    tail = "B" * 2000
    adapter = make_seatalk_adapter(fake_seatalk)
    live = _live(adapter)
    try:
        await live.update("A")
        leftover = await live.close(f"{head}\n\n{tail}")
    finally:
        await adapter.stop()

    final = fake_seatalk.update_stream_calls[-1][1]
    assert final["finish"] is True
    content = final["message"]["text"]["content"]
    assert content == head  # the paragraph that fits, whole
    assert len(content.encode("utf-8")) <= 4096  # inside the platform's stream cap
    assert leftover == tail  # …and the rest goes out the ordinary way


async def test_stream_finish_renders_seatalk_markdown(fake_seatalk: FakeSeaTalk) -> None:
    # The streamed message IS the reply, so its final snapshot is rendered like
    # any other SeaTalk send (interim snapshots stay plain).
    adapter = make_seatalk_adapter(fake_seatalk)
    live = _live(adapter)
    try:
        await live.update("## Result")
        await live.close("## Result\n\nthe file is some_name.py")
    finally:
        await adapter.stop()

    # The interim snapshot opens the stream exactly as it arrived — format 1 now,
    # but with every marker escaped, so a reply cut mid-word still cannot be
    # parsed as half a markdown run.
    opening = fake_seatalk.init_stream_calls[0][1]["message"]["text"]
    assert opening == {"format": 1, "content": "## Result"}
    final = fake_seatalk.update_stream_calls[-1][1]["message"]["text"]
    assert final == {"format": 1, "content": "**Result**\n\nthe file is some\\_name.py"}


async def test_group_stream_uses_the_group_surface_and_threads_the_message(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    live = _live(adapter, chat_id="gid-1", thread_id="t1", chat_kind="group")
    try:
        await live.update("working")
        await live.close("done")
    finally:
        await adapter.stop()

    assert [surface for surface, _ in fake_seatalk.init_stream_calls] == ["group_chat"]
    # thread_id rides INSIDE the message body — the placement verified for sends
    # and the one the platform's own sample uses.
    assert fake_seatalk.init_stream_calls[0][1] == {
        "group_id": "gid-1",
        "message": {
            "tag": "text",
            "text": {"format": 1, "content": "working"},
            "thread_id": "t1",
        },
    }
    assert [surface for surface, _ in fake_seatalk.update_stream_calls] == ["group_chat"]
    # A group update names the group, and nothing else: the stream is already
    # bound to its thread, so an update carries no thread_id of its own.
    assert all(
        body["group_id"] == "gid-1" and "thread_id" not in body["message"]
        for _s, body in fake_seatalk.update_stream_calls
    )
    assert fake_seatalk.single_chat_calls == []  # a group stream never hits single_chat


async def test_open_live_text_is_declared_and_returns_a_stream_surface(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        # supports_edit stays literally false — SeaTalk still cannot rewrite a
        # delivered message — while the live-text capability is what the core asks.
        assert adapter.capabilities.supports_edit is False
        assert adapter.capabilities.supports_live_text is True
        live = await adapter.open_live_text("emp-1")
        assert isinstance(live, SeaTalkLiveText)
    finally:
        await adapter.stop()


async def test_closing_with_no_final_text_finishes_on_the_last_snapshot(
    fake_seatalk: FakeSeaTalk,
) -> None:
    # A reply whose text was entirely a file marker leaves nothing to say, but
    # the stream still has to be finished — it closes on what it already showed.
    adapter = make_seatalk_adapter(fake_seatalk)
    live = _live(adapter)
    try:
        await live.update("uploading the chart")
        leftover = await live.close("")
    finally:
        await adapter.stop()

    final = fake_seatalk.update_stream_calls[-1][1]
    assert final["finish"] is True
    assert final["message"]["text"]["content"] == "uploading the chart"
    assert leftover == ""


async def test_a_silent_stream_is_kept_alive_inside_the_30_second_limit(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """SeaTalk terminates a stream that goes 30 s without an update, and a
    terminated stream cannot be resumed — so a turn that is busy in a tool
    re-sends its last snapshot on a keep-alive instead of losing the surface."""
    adapter = make_seatalk_adapter(fake_seatalk)
    live = SeaTalkLiveText(adapter._post, "emp-1", now=_ticking(), keepalive_seconds=0.01)
    try:
        await live.update("⏳ Bash · building")
        await wait_until(lambda: len(fake_seatalk.update_stream_calls) > 2)
        leftover = await live.close("done")
    finally:
        await adapter.stop()

    bodies = [body for _s, body in fake_seatalk.update_stream_calls]
    # Every keep-alive re-sends the SAME snapshot under the next seq, and the
    # stream is still alive at the end (its finish is accepted).
    assert bodies[1]["message"]["text"]["content"] == "⏳ Bash · building"
    assert [b["seq"] for b in bodies] == list(range(1, len(bodies) + 1))
    assert bodies[-1]["finish"] is True
    assert leftover == ""


# -- FR-070: @mentioning the asker in a group reply ---------------------------


@pytest.mark.acceptance(
    spec="channels",
    scenario="a cross-organisation sender is still identified for a mention",
)
async def test_group_mention_keeps_the_seatalk_id_when_employee_code_and_email_are_empty(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """The event docs warn that ``employee_code`` and ``email`` arrive EMPTY for
    a sender outside the bot's organisation — ``seatalk_id`` is the only id such
    a message carries. Coffer used to keep the two that can be blank and discard
    the one that cannot, which threw away exactly the id a mention needs."""
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    envelope = _group_mention_envelope(plain_text="@bot hi", username="bot")
    envelope["event"]["message"]["sender"] = {
        "seatalk_id": "st-outsider",
        "employee_code": "",
        "email": "",
        "sender_type": 1,
    }
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(envelope)
    finally:
        await adapter.stop()

    [msg] = recorder.messages
    assert msg.sender_mention_id == "st-outsider"
    # …while the two ids the owner gate and the display name use stay empty,
    # which is what the gate is entitled to refuse on. The address-keyed mention
    # fallback is empty for the same reason, which is why it is only a fallback.
    assert msg.sender_id == ""
    assert msg.sender_mention_email == ""
    assert msg.sender_display == "st-outsider"


async def test_group_mention_carries_the_seatalk_id_alongside_the_employee_code(
    fake_seatalk: FakeSeaTalk,
) -> None:
    # The ordinary case: both are present and they are DIFFERENT values, which
    # is why the mention id cannot ride on ``sender_id``.
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(_group_mention_envelope(plain_text="@bot hi", username="bot"))
    finally:
        await adapter.stop()

    [msg] = recorder.messages
    assert (msg.sender_id, msg.sender_mention_id) == ("emp-2", "st-1")
    # The address rides along as the fallback for the case above, where the id
    # is the only thing that arrives.
    assert msg.sender_mention_email == msg.sender_display


async def test_a_dm_carries_no_mention_id(fake_seatalk: FakeSeaTalk) -> None:
    """Nothing to disambiguate in a 1:1 chat, so nothing is carried for it."""
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
                    "seatalk_id": "st-1",
                    "message": {
                        "tag": "text",
                        "message_id": "pm-9",
                        "text": {"content": "hello"},
                    },
                },
            }
        )
    finally:
        await adapter.stop()

    [msg] = recorder.messages
    assert msg.sender_mention_id == ""


def test_the_mention_template_matches_the_documented_tag() -> None:
    """The shape of the tag, pinned to the send-message docs' own sample:
    ``<mention-tag target="seatalk://user?id=0"/>``, self-closing and carrying
    no visible text of its own.

    The page documents THREE targets: by id, by email, and ``id=0`` for every
    member of the group. Coffer builds the first two and never the third — "@All"
    only notifies when the group has "Notify all members with @All" switched on,
    so a bot reply built on it would be silent in most groups and a shout in the
    rest.
    """
    assert (
        SEATALK_MENTION_TEMPLATE.replace("{user_id}", "0")
        == '<mention-tag target="seatalk://user?id=0"/>'
    )
    assert (
        SEATALK_MENTION_EMAIL_TEMPLATE.replace("{user_id}", "ada@example.com")
        == '<mention-tag target="seatalk://user?email=ada@example.com"/>'
    )


async def test_a_group_send_delivers_the_mention_tag_verbatim_as_markdown(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """The tag is markdown — it must reach the wire as ``format: 1`` AND survive
    the SeaTalk markdown renderer byte for byte. That renderer escapes every
    leftover formatting marker with a backslash, so a tag it decided to touch
    would arrive as visible source rather than as a name."""
    adapter = make_seatalk_adapter(fake_seatalk)
    mention = SEATALK_MENTION_TEMPLATE.replace("{user_id}", "st-77")
    try:
        await adapter.send_text(
            "gid-1", f"{mention} the **answer**", thread_id="t1", chat_kind="group"
        )
    finally:
        await adapter.stop()

    [(body, _auth)] = fake_seatalk.group_chat_calls
    assert body["group_id"] == "gid-1"
    assert body["message"]["text"] == {
        "format": 1,
        "content": '<mention-tag target="seatalk://user?id=st-77"/> the **answer**',
    }


@pytest.mark.acceptance(
    spec="channels",
    scenario="an @ notification needs the mention in the message that creates it",
)
async def test_a_stream_carries_the_mention_from_the_message_it_is_created_as(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """SeaTalk decides @ notifications when the message is CREATED, so the tag has
    to be in what ``init_stream`` posts. Shipped the other way round, the tag sat
    on the finished snapshot only: it RENDERED as a blue, tappable name — the
    client shows the content it has — and notified nobody at all.

    That makes every snapshot ``format: 1``, and the in-flight ones safe by
    ESCAPING the partial text instead of asking for plain text."""
    adapter = make_seatalk_adapter(fake_seatalk)
    mention = SEATALK_MENTION_TEMPLATE.replace("{user_id}", "st-77")
    live = _live(adapter, "gid-1", chat_kind="group", thread_id="t1")
    try:
        await live.update(f"{mention} I found")
        await live.update(f"{mention} I found **bo")
        leftover = await live.close(f"{mention} I found **bold** cats.")
    finally:
        await adapter.stop()

    assert leftover == ""
    # The message is created already mentioning the asker.
    opening = fake_seatalk.init_stream_calls[0][1]["message"]["text"]
    assert opening == {"format": 1, "content": f"{mention} I found"}
    bodies = [body["message"]["text"] for _surface, body in fake_seatalk.update_stream_calls]
    # Every snapshot is rich, and keeps the mention, so it never blinks out.
    assert all(t["format"] == 1 and t["content"].startswith(mention) for t in bodies)
    # The interim one is ESCAPED: a half-written bold run reaches the chat as the
    # characters the agent has written so far, not as markup the client must
    # guess at. One backslash per marker — two would show one of them.
    assert bodies[0]["content"] == f"{mention} I found \\*\\*bo"
    assert "\\\\" not in bodies[0]["content"]
    # …while the finished one is RENDERED, bold and all, and its tag survives.
    assert bodies[-1]["content"] == f"{mention} I found **bold** cats."
    assert bodies[-1]["content"].count("mention-tag") == 1


async def test_a_mention_target_with_an_underscore_is_never_escaped(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """Both documented targets can hold a character the SeaTalk markdown escaper
    would otherwise take: an id may contain ``_`` and an address routinely does.
    An escaped tag reaches the reader as visible source, so neither path may
    touch it — the interim (escape-only) one or the final (render) one."""
    adapter = make_seatalk_adapter(fake_seatalk)
    by_id = SEATALK_MENTION_TEMPLATE.replace("{user_id}", "abc_def")
    by_email = SEATALK_MENTION_EMAIL_TEMPLATE.replace("{user_id}", "ada_l@example.com")
    live = _live(adapter, "gid-1", chat_kind="group", thread_id="t1")
    try:
        await live.update(f"{by_id} thinking")
        await live.close(f"{by_email} done_here")
    finally:
        await adapter.stop()

    assert fake_seatalk.init_stream_calls[0][1]["message"]["text"]["content"] == (
        f"{by_id} thinking"
    )
    final = fake_seatalk.update_stream_calls[-1][1]["message"]["text"]["content"]
    # The tag verbatim; the BODY's underscore still escaped, as it must be.
    assert final == f"{by_email} done\\_here"


async def test_an_interim_snapshot_past_the_budget_keeps_its_mention(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """An in-flight snapshot is clipped from the FRONT (it shows the newest
    words), which is exactly where the mention lives. Clip the body, not the
    tag — otherwise a long reply loses the mention halfway through the stream."""
    adapter = make_seatalk_adapter(fake_seatalk)
    mention = SEATALK_MENTION_TEMPLATE.replace("{user_id}", "st-77")
    live = _live(adapter, "gid-1", chat_kind="group", thread_id="t1")
    try:
        await live.update(f"{mention} {'A' * 5000}")
        await live.close(f"{mention} {'A' * 5000}")
    finally:
        await adapter.stop()

    opening = fake_seatalk.init_stream_calls[0][1]["message"]["text"]["content"]
    assert opening.startswith(mention)
    assert "…" in opening  # the body was clipped, the tag kept
    assert len(opening) <= 4096  # inside the platform's stream cap
