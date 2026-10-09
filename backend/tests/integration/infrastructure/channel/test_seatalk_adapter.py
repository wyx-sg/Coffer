"""SeaTalkAdapter against an in-process fake Open API (no real network).

Covers app_access_token caching + refresh-on-code-100, 429 backoff, the
single_chat text/interactive_message payloads, and handle_event
normalization of subscriber messages and approval clicks.
"""

from __future__ import annotations

import dataclasses
import pathlib
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.envelopes import InboundLifecycle
from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel.seatalk_send import (
    SEATALK_MENTION_EMAIL_TEMPLATE,
    SEATALK_MENTION_TEMPLATE,
)

from .conftest import FakeSeaTalk, RecordingCallbacks, make_seatalk_adapter


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


async def test_delete_is_an_unsupported_capability(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
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
    """Per "Download every inbound SeaTalk media type": the media collector returns
    a downloadable ref for an image, a directly-sent file (with its filename + a
    non-image mime), and — best effort — any other tag whose sub-dict carries a
    file-URL content (voice/video), recursing forwarded records. A plain text
    message yields nothing."""
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


@pytest.mark.acceptance(spec="channels/seatalk", scenario="an inbound SeaTalk file drives a turn")
async def test_handle_event_direct_file_downloads_attachment(
    fake_seatalk: FakeSeaTalk, tmp_path: Any
) -> None:
    """Per "Download every inbound SeaTalk media type": a directly-sent file (not an
    image) is fetched (authenticated) and attached with its real filename + a
    non-image mime, so it drives a turn like a photo does instead of hitting the
    "unsupported message" branch. Uses the live-captured shape:
    ``message.file.content`` is the auth-gated URL and ``message.file.filename`` the
    original name."""
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


# -- outbound media -------------------------------------------------------------


async def test_send_media_image_posts_group_image_with_thread_in_body(
    fake_seatalk: FakeSeaTalk, tmp_path: Any
) -> None:
    """Per "Upload outbound media into the originating chat and thread": a returned
    image during a group-thread turn is uploaded as a SeaTalk ``image`` message
    (base64 content) to group_chat, with thread_id INSIDE the message body so it
    lands in the originating thread."""
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
    """Per "Identify a thread by its root message": a DM reply sent inside a thread
    must carry thread_id on the single_chat message body so SeaTalk threads it —
    documented wire placement, not yet live-verified against the real platform."""
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


async def test_capabilities_declare_history_fetch(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
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
    """Per spec channels "Route group selection-card taps back to the group": a card
    tapped in a GROUP arrives with a ``group_id`` (mirroring the group @mention
    event) and the tapper under ``sender`` — the adapter normalizes it to a group
    callback (chat_kind="group", chat_id=group_id, thread_id set, sender_id = the
    tapper's employee_code) so the core owner-gates and replies in the group thread,
    not a DM."""
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


# -- inbound de-duplication (spec channels "Process each inbound event once") ---


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
    """SeaTalk retries a slow callback, so the SAME event_id can arrive twice — the
    second delivery must be dropped, driving the turn once. Two DIFFERENT event_ids
    remain two turns."""
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


async def _read_with_media(adapter: Any, chat_id: str, thread_id: str, **kwargs: Any) -> Any:
    """Read a thread and download every message's media, as the core does for
    the messages it keeps: (flattened items, attachments)."""
    read = await adapter.fetch_thread(chat_id, thread_id, **kwargs)
    items = [item for message in read.messages for item in message.items]
    atts: tuple[Any, ...] = ()
    for message in read.messages:
        atts += await adapter.fetch_message_media(message)
    return items, atts


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
        items, atts = await _read_with_media(adapter, "gid-1", "t1")
    finally:
        await adapter.stop()
    assert [(it.sender, it.text) for it in items] == [
        ("alice@example.com", "in the thread"),
        ("bob@example.com", "replying"),
    ]
    assert atts == ()  # a text-only thread downloads nothing
    [params] = fake_seatalk.thread_calls
    assert params == {"group_id": "gid-1", "thread_id": "t1", "page_size": "100"}


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
        items, _atts = await _read_with_media(adapter, "gid-1", "t1")
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
    """Per spec channels "Download the media a thread's messages carry": when the
    @mention lands inside a thread, the images the thread's own messages carry — a
    directly-sent image AND one buried in a forwarded record — are downloaded
    (authenticated) and returned as the second tuple element, so a picture in the
    thread reaches the vision agent as real bytes instead of a dead auth-gated file
    link."""
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
        items, atts = await _read_with_media(adapter, "gid-1", "t1")
    finally:
        await adapter.stop()
    # Text still flattens (the leaf image in the forwarded record contributes no text).
    assert ("owner@example.com", "look at these") in [(it.sender, it.text) for it in items]
    # Both images downloaded — the direct one and the one nested in the forward.
    assert fake_seatalk.file_downloads == ["direct1", "fwd1"]  # ?seq=3 is a query param
    assert len(atts) == 2
    assert all(a.mime == "image/png" for a in atts)
    assert all(pathlib.Path(a.path).read_bytes() == fake_seatalk.file_bytes for a in atts)


async def test_message_to_item_maps_non_text_tags() -> None:
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
    """Deduplication ("Process each inbound event once") covers these like every
    other event — a retried callback must not report the same removal twice."""
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
        fetched = await adapter.fetch_thread("emp-1", "t1", chat_kind="direct")
    finally:
        await adapter.stop()
    assert fetched.messages == ()
    assert dm_thread == [{"employee_code": "emp-1", "thread_id": "t1", "page_size": "100"}]
    assert fake_seatalk.thread_calls == []  # the group endpoint stayed untouched


async def test_fetch_thread_degrades_to_empty_list_on_error(
    fake_seatalk: FakeSeaTalk, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any transport/parse/permission error must never break a group turn —
    fetch_thread reports a failed read, which the turn runs without."""
    adapter = make_seatalk_adapter(fake_seatalk)

    async def _boom(*args: object, **kwargs: object) -> Any:
        raise ChannelSendFailed("st", "group_chat/get_thread_by_thread_id: code=103 http=200")

    monkeypatch.setattr(adapter, "_context", dataclasses.replace(adapter._context, get=_boom))
    try:
        assert (await adapter.fetch_thread("gid-1", "t1")).failed
    finally:
        await adapter.stop()


# -- no live surface ("Show only typing while a turn runs") -------------------


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="a seatalk transport offers no live surface"
)
async def test_seatalk_offers_no_live_surface(fake_seatalk: FakeSeaTalk) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        assert adapter.capabilities.supports_live_text is False
        assert await adapter.open_live_text("emp-1") is None
        assert await adapter.open_live_text("gid-1", thread_id="t1", chat_kind="group") is None
    finally:
        await adapter.stop()
    assert fake_seatalk.init_stream_calls == []
    assert fake_seatalk.update_stream_calls == []


# -- @mentioning the asker in a group reply ("Mention the asker in a group answer")


@pytest.mark.acceptance(
    spec="channels/seatalk",
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


async def test_a_mention_target_with_an_underscore_is_never_escaped(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """Both documented targets can hold a character the SeaTalk markdown escaper
    would otherwise take: an id may contain ``_`` and an address routinely does.
    An escaped tag reaches the reader as visible source, so rendering must leave
    it alone while still escaping the body around it."""
    adapter = make_seatalk_adapter(fake_seatalk)
    by_id = SEATALK_MENTION_TEMPLATE.replace("{user_id}", "abc_def")
    by_email = SEATALK_MENTION_EMAIL_TEMPLATE.replace("{user_id}", "ada_l@example.com")
    try:
        await adapter.send_text("gid-1", f"{by_id} thinking", thread_id="t1", chat_kind="group")
        await adapter.send_text("gid-1", f"{by_email} done_here", thread_id="t1", chat_kind="group")
    finally:
        await adapter.stop()

    contents = [body["message"]["text"]["content"] for body, _ in fake_seatalk.group_chat_calls]
    # The tags verbatim; the BODY's underscore still escaped, as it must be.
    assert contents == [f"{by_id} thinking", f"{by_email} done\\_here"]


# -- group replies as withdrawable cards ---------------------------------------


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="a group reply is cards with the trash button on the last"
)
async def test_a_long_group_reply_is_cards_with_the_trash_button_on_the_last(
    fake_seatalk: FakeSeaTalk,
) -> None:
    from coffer.domain.channel.envelopes import ChoiceButton

    reply = "\n\n".join(f"paragraph {i} " + "word " * 120 for i in range(12))
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        sent = await adapter.send_text(
            "gid-1",
            reply,
            chat_kind="group",
            thread_id="t1",
            buttons=[ChoiceButton(label="🗑", value="del:r1")],
        )
    finally:
        await adapter.stop()

    cards = [body["message"] for body, _auth in fake_seatalk.group_chat_calls]
    assert len(cards) > 1
    assert all(card["tag"] == "interactive_message" for card in cards)
    assert len(sent.all_ids) == len(cards)
    elements = [card["interactive_message"]["elements"] for card in cards]
    for card_elements in elements:
        descriptions = [e for e in card_elements if e["element_type"] == "description"]
        assert 1 <= len(descriptions) <= 4
        assert all(len(d["description"]["text"]) <= 1000 for d in descriptions)
    has_buttons = [any(e["element_type"] == "button_group" for e in els) for els in elements]
    assert has_buttons == [False] * (len(cards) - 1) + [True]
    assert elements[1][0]["description"]["text"].startswith("(2/")


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="a short group reply is one card with markdown rendered"
)
async def test_a_short_group_reply_is_one_rendered_card(fake_seatalk: FakeSeaTalk) -> None:
    from coffer.domain.channel.envelopes import ChoiceButton

    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.send_text(
            "gid-1",
            "Deploy is **green**.\n\n```\nok\n```",
            chat_kind="group",
            buttons=[ChoiceButton(label="🗑", value="del:r1")],
        )
    finally:
        await adapter.stop()

    [(body, _auth)] = fake_seatalk.group_chat_calls
    description = body["message"]["interactive_message"]["elements"][0]["description"]
    assert description["format"] == 1
    assert "**green**" in description["text"] and "```" in description["text"]


@pytest.mark.acceptance(spec="channels/seatalk", scenario="withdrawing rewrites each card blank")
async def test_withdrawing_rewrites_the_card_blank_through_update_message(
    fake_seatalk: FakeSeaTalk,
) -> None:
    updates: list[dict[str, Any]] = []

    async def handler(request: Request) -> JSONResponse:
        updates.append(await request.json())
        return JSONResponse(content={"code": 0})

    fake_seatalk.app.post("/messaging/v2/update")(handler)
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.withdraw_message("gid-1", "mid-9", chat_kind="group")
    finally:
        await adapter.stop()

    [body] = updates
    assert body["message_id"] == "mid-9"
    elements = body["message"]["interactive_message"]["elements"]
    assert elements == [
        {"element_type": "description", "description": {"format": 1, "text": "🗑 Withdrawn"}}
    ]


@pytest.mark.acceptance(spec="channels/seatalk", scenario="a seatalk group turn does not stream")
async def test_seatalk_declares_no_group_streaming_and_a_seven_day_card_window(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        caps = adapter.capabilities
    finally:
        await adapter.stop()
    assert caps.supports_live_text is False  # typing only, in groups and direct chats
    assert caps.withdraw_window_hours == 168
    assert caps.withdraw_removes is False


async def test_open_thread_anchored_replies_in_the_owners_message_thread(
    fake_seatalk: FakeSeaTalk,
) -> None:
    """With the owner's own message as anchor the mark is a reply in its thread
    and that message's id is the thread's; without one a root message is posted
    and its id is the thread's."""
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        anchored = await adapter.open_thread("emp-1", "🧵#1 Task", "body", anchor_message_id="u-1")
        rooted = await adapter.open_thread("emp-1", "🧵#2 Task", "body")
    finally:
        await adapter.stop()
    [(first, _a), (second, _b)] = fake_seatalk.single_chat_calls
    assert anchored == "u-1"
    assert first["message"]["thread_id"] == "u-1"
    assert first["message"]["text"]["content"].startswith("🧵#1 Task")
    assert "thread_id" not in second["message"] or not second["message"]["thread_id"]
    assert rooted != "u-1" and rooted
