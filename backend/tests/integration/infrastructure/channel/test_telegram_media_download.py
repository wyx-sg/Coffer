"""Inbound Telegram media downloads that fail (spec channels, FR-067).

The file endpoint's URL carries the bot token (``/file/bot<token>/<path>``),
so a failed download is the one place the adapter could put the token into the
daemon log by accident: an httpx status error's message quotes the request URL,
and a traceback logged with ``exc_info`` carries that message. These tests
drive a photo message through the real poll loop against the in-process fake
Bot API with the file endpoint broken on cue, and assert both halves of the
contract — the turn still happens with a note, and no log record carries the
token.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
import pytest

from coffer.infrastructure.channel.telegram import TelegramAdapter

from .conftest import FakeTelegram, RecordingCallbacks, wait_until

#: Distinctive enough that its presence anywhere in a log record is unambiguous.
_TOKEN = "123456:SECRET-BOT-TOKEN-DO-NOT-LOG"


class _BrokenFileEndpoint(httpx.AsyncBaseTransport):
    """Bot API method calls reach the fake; the file endpoint fails on cue.

    ``failure`` is either an HTTP status to answer the download with, or a
    factory for the transport error to raise instead (a connection refused, a
    read timeout, ...).
    """

    def __init__(
        self, fake: FakeTelegram, failure: int | Callable[[httpx.Request], httpx.HTTPError]
    ) -> None:
        self._inner = httpx.ASGITransport(app=fake.app)
        self._failure = failure

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/file/"):
            if isinstance(self._failure, int):
                return httpx.Response(self._failure, content=b"Not Found", request=request)
            raise self._failure(request)
        return await self._inner.handle_async_request(request)


def _adapter(
    fake: FakeTelegram, failure: int | Callable[[httpx.Request], httpx.HTTPError], media_dir
) -> TelegramAdapter:
    client = httpx.AsyncClient(transport=_BrokenFileEndpoint(fake, failure), base_url="http://fake")
    return TelegramAdapter(
        "tg", _TOKEN, client=client, base_url="http://fake", poll_timeout=1, media_dir=media_dir
    )


def _photo_update(update_id: int) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 2000 + update_id,
            "date": 1718000000,
            "chat": {"id": 555},
            "from": {"id": 4242, "first_name": "Yu", "username": "yu"},
            "photo": [
                {"file_id": "small", "file_size": 100},
                {"file_id": "big", "file_size": 9999},
            ],
            "caption": "what is this?",
        },
    }


def _connect_refused(request: httpx.Request) -> httpx.HTTPError:
    return httpx.ConnectError("connection refused", request=request)


@pytest.mark.parametrize(
    "failure",
    [pytest.param(404, id="download-404"), pytest.param(_connect_refused, id="connect-error")],
)
@pytest.mark.acceptance(
    spec="channels", scenario="a failed telegram download never puts the bot token in the log"
)
async def test_a_failed_download_is_noted_without_the_token_reaching_the_log(
    fake_telegram: FakeTelegram,
    caplog: pytest.LogCaptureFixture,
    tmp_path,
    failure: int | Callable[[httpx.Request], httpx.HTTPError],
) -> None:
    recorder = RecordingCallbacks()
    adapter = _adapter(fake_telegram, failure, tmp_path / "media")
    with caplog.at_level(logging.WARNING):
        await fake_telegram.update_batches.put([_photo_update(20)])
        await adapter.start(recorder.as_callbacks())
        try:
            await wait_until(lambda: len(recorder.messages) == 1)
        finally:
            await adapter.stop()

    # Best-effort: the caption still drives a turn, the missing file is said out
    # loud in the turn text, and nothing was saved under the media dir.
    msg = recorder.messages[0]
    assert msg.attachments == ()
    assert "what is this?" in msg.text
    assert "[attachment 'photo.jpg' could not be downloaded]" in msg.text
    assert not (tmp_path / "media").exists()
    # getFile itself succeeded — it is the byte download that failed.
    assert [c.get("file_id") for c in fake_telegram.calls_for("getFile")] == ["big"]

    # The failure is logged (it is not silent)...
    failed = [r for r in caplog.records if r.getMessage() == "telegram.media.download_failed"]
    assert len(failed) == 1
    assert failed[0].channel == "tg"  # type: ignore[attr-defined]
    # ...but nothing in the log carries the token: not the formatted output
    # (which includes any traceback), not the record's message, not its extras.
    assert _TOKEN not in caplog.text
    for record in caplog.records:
        assert _TOKEN not in record.getMessage()
        assert _TOKEN not in str(record.__dict__)
        assert _TOKEN not in (record.exc_text or "")


async def test_a_download_rejected_by_status_says_which_status(
    fake_telegram: FakeTelegram, caplog: pytest.LogCaptureFixture, tmp_path
) -> None:
    """The log line names the status so the owner can tell a revoked file (404)
    from a rate limit (429) — without the URL that would name the token."""
    recorder = RecordingCallbacks()
    adapter = _adapter(fake_telegram, 429, tmp_path / "media")
    with caplog.at_level(logging.WARNING):
        await fake_telegram.update_batches.put([_photo_update(21)])
        await adapter.start(recorder.as_callbacks())
        try:
            await wait_until(lambda: len(recorder.messages) == 1)
        finally:
            await adapter.stop()
    [failed] = [r for r in caplog.records if r.getMessage() == "telegram.media.download_failed"]
    detail = str(failed.__dict__.get("detail", ""))
    assert "429" in detail
    assert _TOKEN not in detail and _TOKEN not in caplog.text
