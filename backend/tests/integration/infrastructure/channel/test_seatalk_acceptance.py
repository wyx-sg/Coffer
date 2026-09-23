"""SeaTalkAdapter acceptance scenarios against the in-process fake Open API.

Each test drives the real adapter over ``httpx.ASGITransport`` into
``FakeSeaTalk`` — no network — and asserts both what the core receives and
what SeaTalk would have been asked.
"""

from __future__ import annotations

import pathlib
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.envelopes import ChoiceButton, InboundLifecycle
from coffer.infrastructure.channel.seatalk_parse import interactive_card

from .conftest import FakeSeaTalk, RecordingCallbacks, make_seatalk_adapter

_FILE_URL = "https://openapi.seatalk.io/messaging/v2/file/"


class _LifecycleRecorder(RecordingCallbacks):
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


def _record_paths(fake: FakeSeaTalk) -> list[str]:
    """Every request path the adapter sends the fake Open API, in order."""
    paths: list[str] = []

    @fake.app.middleware("http")
    async def record(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        paths.append(request.url.path)
        return await call_next(request)

    return paths


# -- cards -----------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels/seatalk",
    scenario="a six-button card is laid out as two button groups with clamped text",
)
def test_a_six_button_card_uses_two_button_groups_and_clamps_text() -> None:
    buttons = [ChoiceButton(label=f"L{i}", value=f"v{i}") for i in range(6)]
    card = interactive_card("B" * 1500, buttons, title="T" * 300)

    elements = card["interactive_message"]["elements"]
    assert isinstance(elements, list)
    # Buttons are elements themselves, never a `buttons` array beside them.
    assert "buttons" not in card["interactive_message"]
    groups = [e for e in elements if e["element_type"] == "button_group"]
    assert [[b["value"] for b in g["button_group"]] for g in groups] == [
        ["v0", "v1", "v2"],
        ["v3", "v4", "v5"],
    ]
    assert [e for e in elements if e["element_type"] == "button"] == []
    [title] = [e for e in elements if e["element_type"] == "title"]
    [desc] = [e for e in elements if e["element_type"] == "description"]
    assert len(title["title"]["text"]) == 120
    assert len(desc["description"]["text"]) == 1000


# -- thread media ----------------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels/seatalk",
    scenario="a file posted earlier in a seatalk thread is attached to the turn",
)
async def test_a_thread_file_and_a_forwarded_image_are_attached(
    fake_seatalk: FakeSeaTalk, tmp_path: Any
) -> None:
    fake_seatalk.thread_response = {
        "code": 0,
        "thread_messages": [
            {
                "sender": {"email": "owner@example.com"},
                "tag": "text",
                "text": {"plain_text": "here is the report"},
            },
            {
                "sender": {"email": "owner@example.com"},
                "tag": "file",
                "file": {"content": _FILE_URL + "report1", "filename": "report.pdf"},
            },
            {
                "tag": "combined_forwarded_chat_history",
                "sender": {"email": "owner@example.com"},
                "combined_forwarded_chat_history": {
                    "content": [
                        {
                            "tag": "image",
                            "sender": {"email": "j@example.com"},
                            "image": {"content": _FILE_URL + "fwdimg"},
                        }
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

    # Both downloaded with the app token, and attached.
    assert sorted(fake_seatalk.file_downloads) == ["fwdimg", "report1"]
    assert len(atts) == 2
    by_name = {a.filename: a for a in atts}
    assert "report.pdf" in by_name
    assert not by_name["report.pdf"].mime.startswith("image/")
    assert any(a.mime.startswith("image/") for a in atts)
    assert all(pathlib.Path(a.path).read_bytes() == fake_seatalk.file_bytes for a in atts)
    # The flattened thread text still reaches the turn.
    assert ("owner@example.com", "here is the report") in [(i.sender, i.text) for i in items]


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="an image nested two forwards deep is downloaded"
)
async def test_an_image_two_forwards_deep_is_downloaded(
    fake_seatalk: FakeSeaTalk, tmp_path: Any
) -> None:
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
                        "message_id": "pm-deep",
                        "combined_forwarded_chat_history": {
                            "content": [
                                {
                                    "tag": "combined_forwarded_chat_history",
                                    "sender": {"email": "a@example.com"},
                                    "combined_forwarded_chat_history": {
                                        "content": [
                                            {
                                                "tag": "text",
                                                "sender": {"email": "b@example.com"},
                                                "text": {"content": "look at this"},
                                            },
                                            {
                                                "tag": "image",
                                                "sender": {"email": "b@example.com"},
                                                "image": {"content": _FILE_URL + "deep1"},
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
    assert fake_seatalk.file_downloads == ["deep1"]
    [att] = msg.attachments
    assert att.mime.startswith("image/")
    assert pathlib.Path(att.path).read_bytes() == fake_seatalk.file_bytes
    assert msg.text.startswith("[Forwarded chat record]")
    assert "b@example.com: look at this" in msg.text


# -- threads ---------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="a DM thread is read from the direct-chat thread endpoint"
)
async def test_a_dm_thread_reads_only_the_direct_chat_thread_endpoint(
    fake_seatalk: FakeSeaTalk,
) -> None:
    dm_calls: list[dict[str, Any]] = []

    async def dm_thread(request: Request) -> JSONResponse:
        dm_calls.append(dict(request.query_params))
        return JSONResponse(content={"code": 0, "thread_messages": []})

    fake_seatalk.app.get("/messaging/v2/single_chat/get_thread_by_thread_id")(dm_thread)
    paths = _record_paths(fake_seatalk)
    adapter = make_seatalk_adapter(fake_seatalk)
    try:
        await adapter.fetch_thread("emp-1", "t1", limit=20, chat_kind="direct")
    finally:
        await adapter.stop()

    assert dm_calls == [{"employee_code": "emp-1", "thread_id": "t1", "page_size": "20"}]
    assert fake_seatalk.thread_calls == []  # the group-thread endpoint is untouched
    # Beyond the token grant, the DM thread read is the only call made: no
    # group-thread read and no group-chat history read of any kind.
    assert [p for p in paths if p != "/auth/app_access_token"] == [
        "/messaging/v2/single_chat/get_thread_by_thread_id"
    ]


@pytest.mark.acceptance(
    spec="channels/seatalk",
    scenario="a quoting seatalk message keeps the quoted id on the envelope",
)
async def test_a_quoting_dm_and_group_message_keep_the_quoted_id(
    fake_seatalk: FakeSeaTalk,
) -> None:
    paths = _record_paths(fake_seatalk)
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_id": "ev-dm",
                "event_type": "message_from_bot_subscriber",
                "timestamp": 1718000000,
                "event": {
                    "employee_code": "emp-1",
                    "message": {
                        "tag": "text",
                        "message_id": "pm-2",
                        "quoted_message_id": "pm-1",
                        "text": {"content": "about this"},
                    },
                },
            }
        )
        await adapter.handle_event(
            {
                "event_id": "ev-grp",
                "event_type": "new_mentioned_message_received_from_group_chat",
                "timestamp": 1718000000,
                "event": {
                    "group_id": "gid-1",
                    "message": {
                        "message_id": "gm-2",
                        "thread_id": "t-1",
                        "quoted_message_id": "gm-1",
                        "sender": {"seatalk_id": "st-1", "employee_code": "emp-1"},
                        "tag": "text",
                        "text": {
                            "plain_text": "@Bot and this",
                            "mentioned_list": [{"username": "Bot", "seatalk_id": "bot-1"}],
                        },
                    },
                },
            }
        )
    finally:
        await adapter.stop()

    assert [m.quoted_message_id for m in recorder.messages] == ["pm-1", "gm-1"]
    # Normalizing made no call to the platform at all — the quoted body is
    # never fetched by the transport.
    assert paths == []


# -- lifecycle -------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels/seatalk",
    scenario="seatalk removal and external-conversion events become lifecycle events",
)
async def test_removal_and_external_conversion_arrive_as_lifecycle_events(
    fake_seatalk: FakeSeaTalk,
) -> None:
    adapter = make_seatalk_adapter(fake_seatalk)
    recorder = _LifecycleRecorder()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_id": "ev-r",
                "event_type": "bot_removed_from_group_chat",
                "timestamp": 1718000000,
                "event": {"group_id": "gid-1", "remover": {"email": "r@example.com"}},
            }
        )
        await adapter.handle_event(
            {
                "event_id": "ev-x",
                "event_type": "group_chat_converted_to_external_group",
                "timestamp": 1718000000,
                "event": {"group_id": "gid-1"},
            }
        )
    finally:
        await adapter.stop()

    assert [(e.chat_id, e.kind) for e in recorder.lifecycle] == [
        ("gid-1", "removed_from_group"),
        ("gid-1", "group_became_external"),
    ]
    assert recorder.messages == []
    assert recorder.callbacks == []
