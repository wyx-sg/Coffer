"""Tests for SeaTalk context fetching — that a DM thread and a group thread
reach their own endpoints while sharing one body, that every page of a thread is
read, and that a quoted message is resolved by its id.

What is checked here is the routing decision itself, which is pure enough to
exercise with a recording ``get`` instead of a server — the adapter-level
behaviour (flattening, media download, degrade-to-empty) is covered against the
fake SeaTalk server alongside. It lives in the integration tier regardless,
because ``fetch_thread_context`` (like ``fetch_quoted_context``) takes an
``httpx.AsyncClient`` and the unit tier bans that import outright
(``check_unit_purity``); dodging the gate by passing a cast ``None`` would be
lying about the signature to win an argument with a linter.
"""

from __future__ import annotations

import pathlib
import time
from typing import Any

import httpx
import pytest

from coffer.infrastructure.channel.seatalk_history import (
    fetch_quoted_context,
    fetch_thread_context,
    message_media,
    to_thread_message,
)


class _RecordingGet:
    """Stands in for the adapter's authenticated GET, recording the endpoint
    and params it is asked for and replaying canned pages in order (the last one
    repeats)."""

    def __init__(self, *pages: dict[str, Any]) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.pages = list(pages) or [{"code": 0, "thread_messages": []}]

    async def __call__(self, path: str, params: dict[str, Any]) -> Any:
        self.calls.append((path, params))
        return self.pages[min(len(self.calls), len(self.pages)) - 1]


async def _never_called_token() -> str:  # pragma: no cover - a text thread downloads nothing
    raise AssertionError("a text-only thread must not fetch an app token")


def _text_message(email: str, plain_text: str) -> dict[str, Any]:
    return {"sender": {"email": email}, "tag": "text", "text": {"plain_text": plain_text}}


async def _fetch(get: _RecordingGet, tmp_path: pathlib.Path, **kwargs: Any):
    del tmp_path  # a thread read downloads nothing
    return await fetch_thread_context(get, "chat-1", "t1", **kwargs)


def _texts(read: Any) -> list[tuple[str, str]]:
    return [(it.sender, it.text) for m in read.messages for it in m.items]


async def test_group_thread_reads_the_group_endpoint_by_group_id(tmp_path):
    get = _RecordingGet()
    await _fetch(get, tmp_path)
    assert get.calls == [
        (
            "/messaging/v2/group_chat/get_thread_by_thread_id",
            {"group_id": "chat-1", "thread_id": "t1", "page_size": 100},
        )
    ]


async def test_direct_thread_reads_the_single_chat_endpoint_by_employee_code(tmp_path):
    # A SeaTalk DM's chat_id IS the peer's employee_code, so the same argument
    # feeds a differently-named parameter on the single-chat endpoint.
    get = _RecordingGet()
    await _fetch(get, tmp_path, chat_kind="direct")
    assert get.calls == [
        (
            "/messaging/v2/single_chat/get_thread_by_thread_id",
            {"employee_code": "chat-1", "thread_id": "t1", "page_size": 100},
        )
    ]


async def test_group_is_the_default_chat_kind(tmp_path):
    # Callers predating DM threads pass no chat_kind and must keep reading groups.
    get = _RecordingGet()
    await _fetch(get, tmp_path)
    assert get.calls[0][0] == "/messaging/v2/group_chat/get_thread_by_thread_id"


async def test_both_kinds_flatten_the_identical_response_body(tmp_path):
    # The two endpoints answer with the same shape, which is the whole reason
    # one body serves both — assert the DM path flattens it like the group path.
    payload = {
        "code": 0,
        "next_cursor": "",
        "thread_messages": [
            _text_message("alice@example.com", "in the thread"),
            _text_message("bob@example.com", "replying"),
        ],
    }
    expected = [("alice@example.com", "in the thread"), ("bob@example.com", "replying")]
    for kind in ("group", "direct"):
        read = await _fetch(_RecordingGet(payload), tmp_path, chat_kind=kind)
        assert _texts(read) == expected
        assert not any(m.has_media for m in read.messages)


async def test_an_unrecognised_chat_kind_degrades_instead_of_reading_the_wrong_chat(tmp_path):
    get = _RecordingGet()
    assert (await _fetch(get, tmp_path, chat_kind="broadcast")).failed
    assert get.calls == []  # no request went out at all


async def test_a_failing_fetch_degrades_to_empty_on_both_kinds(tmp_path):
    # 4010 ("thread_id names an unthreaded message") and any transport failure
    # alike must leave the turn answerable on the message alone.
    class _Failing(_RecordingGet):
        async def __call__(self, path: str, params: dict[str, Any]) -> Any:
            self.calls.append((path, params))
            raise httpx.HTTPError("boom")

    for kind in ("group", "direct"):
        assert (await _fetch(_Failing(), tmp_path, chat_kind=kind)).failed


def _page(cursor: str, *texts: str) -> dict[str, Any]:
    return {
        "code": 0,
        "next_cursor": cursor,
        "thread_messages": [_text_message("alice@example.com", t) for t in texts],
    }


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="a thread longer than one page is read to its last message"
)
async def test_every_page_of_a_thread_is_read_by_following_next_cursor(tmp_path):
    # Pages run oldest-first, so stopping after page one would drop exactly the
    # messages written just before the @mention.
    get = _RecordingGet(_page("c2", "first", "second"), _page("", "latest"))
    read = await _fetch(get, tmp_path)
    assert [text for _, text in _texts(read)] == ["first", "second", "latest"]
    assert [params.get("cursor") for _, params in get.calls] == [None, "c2"]


async def test_a_cursor_that_never_ends_stops_at_the_page_cap(tmp_path):
    get = _RecordingGet(_page("again", "loop"))
    read = await _fetch(get, tmp_path)
    assert len(get.calls) == 20
    assert len(read.messages) == 20


async def test_a_later_page_failing_keeps_the_pages_already_read(tmp_path):
    class _FailsOnPageTwo(_RecordingGet):
        async def __call__(self, path: str, params: dict[str, Any]) -> Any:
            if params.get("cursor"):
                raise httpx.HTTPError("boom")
            return await super().__call__(path, params)

    read = await _fetch(_FailsOnPageTwo(_page("c2", "older")), tmp_path)
    assert not read.failed
    assert [text for _, text in _texts(read)] == ["older"]


async def _fetch_quoted(get: _RecordingGet, tmp_path: pathlib.Path):
    async with httpx.AsyncClient() as client:
        return await fetch_quoted_context(get, client, tmp_path, _never_called_token, "mq-1")


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="a quoted seatalk message is resolved by its id"
)
async def test_a_quoted_message_is_resolved_by_its_id(tmp_path):
    # The body has a thread message's shape (sender, tag, text.plain_text).
    get = _RecordingGet({"code": 0, **_text_message("alice@example.com", "讲个笑话")})
    items, atts = await _fetch_quoted(get, tmp_path)
    assert get.calls == [("/messaging/v2/get_message_by_message_id", {"message_id": "mq-1"})]
    assert [(it.sender, it.text) for it in items] == [("alice@example.com", "讲个笑话")]
    assert atts == ()


async def test_a_quoted_message_that_cannot_be_read_degrades_to_empty(tmp_path):
    class _Failing(_RecordingGet):
        async def __call__(self, path: str, params: dict[str, Any]) -> Any:
            raise httpx.HTTPError("boom")

    assert await _fetch_quoted(_Failing(), tmp_path) == ([], ())
    assert await _fetch_quoted(_RecordingGet({"code": 4010}), tmp_path) == ([], ())


@pytest.mark.acceptance(
    spec="channels",
    scenario="a thread older than the platform's 7-day reach says what it cannot show",
)
async def test_thread_older_than_seven_days_carries_a_note(tmp_path):
    now = time.time()
    root = {**_text_message("a@x.com", "/dod"), "message_sent_time": now - 14 * 86400}
    reply = {**_text_message("b@x.com", "hi"), "message_sent_time": now - 60}
    get = _RecordingGet({"code": 0, "next_cursor": "", "thread_messages": [root, reply]})

    read = await _fetch(get, tmp_path)

    assert [m.sender for m in read.messages] == ["a@x.com", "b@x.com"]
    assert "7 days" in read.window_note


async def test_recent_thread_carries_no_note(tmp_path):
    now = time.time()
    root = {**_text_message("a@x.com", "start"), "message_sent_time": now - 3600}
    get = _RecordingGet({"code": 0, "next_cursor": "", "thread_messages": [root]})

    read = await _fetch(get, tmp_path)

    assert [m.sender for m in read.messages] == ["a@x.com"]
    assert read.window_note == ""


def test_a_thread_message_carries_its_id_time_and_whether_the_bot_sent_it():
    message = {
        **_text_message("", "done"),
        "message_id": "m-9",
        "message_sent_time": 1_700_000_000,
        "sender": {"sender_type": 2},
    }
    converted = to_thread_message(message)
    assert converted.message_id == "m-9"
    assert converted.sent_at is not None and converted.sent_at.timestamp() == 1_700_000_000
    assert converted.from_bot is True
    assert converted.sender == "bot"
    assert converted.has_media is False


async def test_a_text_message_downloads_no_media(tmp_path):
    message = to_thread_message(_text_message("a@x.com", "hi"))
    async with httpx.AsyncClient() as client:
        assert await message_media(client, tmp_path, _never_called_token, message) == ()
