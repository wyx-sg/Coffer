"""Shared in-process platform fakes for channel transport tests (spec channels).

``FakeTelegram`` / ``FakeSeaTalk`` are small FastAPI apps mounted via
``httpx.ASGITransport`` — the adapters talk to them exactly as they would
talk to the real platform APIs, with zero real network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.envelopes import InboundCallback, InboundMessage
from coffer.infrastructure.channel.seatalk import SeaTalkAdapter
from coffer.infrastructure.channel.telegram import TelegramAdapter


async def wait_until(
    predicate: Callable[[], bool], *, timeout: float = 5.0, interval: float = 0.02
) -> None:
    """Deterministic poll-wait: fail loudly instead of sleeping blind."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


class RecordingCallbacks:
    """AdapterCallbacks target that captures the normalized envelopes."""

    def __init__(self) -> None:
        self.messages: list[InboundMessage] = []
        self.callbacks: list[InboundCallback] = []

    async def on_message(self, message: InboundMessage) -> None:
        self.messages.append(message)

    async def on_callback(self, callback: InboundCallback) -> None:
        self.callbacks.append(callback)

    def as_callbacks(self) -> AdapterCallbacks:
        return AdapterCallbacks(on_message=self.on_message, on_callback=self.on_callback)


class FakeTelegram:
    """Scriptable in-process Bot API: serves getUpdates from a queue, records
    every method call, and can reject HTML parse_mode or fail polls on cue."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.update_batches: asyncio.Queue[list[dict[str, Any]]] = asyncio.Queue()
        self.reject_html_sends = 0  # reject sendMessage with parse_mode=HTML N times
        self.reject_all_sends = 0  # reject any sendMessage N times
        self.fail_get_updates = 0  # answer getUpdates with HTTP 500 N times
        self.bad_payload_get_updates = False  # answer getUpdates ok:true with a non-list result
        self.html_error_sends = 0  # answer sendMessage with a non-JSON HTML body N times
        self._next_message_id = 100
        self.file_bytes = b"FAKE-IMAGE-BYTES"  # served for any file download
        self.app = FastAPI()
        self.app.post("/bot{token}/{method}")(self._handle)
        self.app.get("/file/bot{token}/{file_path:path}")(self._serve_file)

    async def _serve_file(self, token: str, file_path: str) -> Response:
        return Response(content=self.file_bytes, media_type="application/octet-stream")

    async def _handle(self, token: str, method: str, request: Request) -> JSONResponse:
        # sendPhoto/sendDocument upload multipart (data + files); everything
        # else posts JSON. Parse whichever the request carries so the recorded
        # ``params`` are the flat field dict either way.
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            form = await request.form()
            params: dict[str, Any] = {k: v for k, v in form.items() if isinstance(v, str)}
        else:
            params = await request.json()
        self.calls.append((method, params))
        if method == "getUpdates":
            if self.bad_payload_get_updates:
                # A well-formed envelope whose result is not a list of updates.
                return JSONResponse(content={"ok": True, "result": {}})
            if self.fail_get_updates > 0:
                self.fail_get_updates -= 1
                return JSONResponse(status_code=500, content={"ok": False, "description": "boom"})
            try:  # long poll: hold briefly, then answer empty — no busy spin
                batch = await asyncio.wait_for(self.update_batches.get(), timeout=0.2)
            except TimeoutError:
                batch = []
            return JSONResponse(content={"ok": True, "result": batch})
        if method == "sendMessage":
            if self.html_error_sends > 0:
                # A gateway returns a 502 HTML page, not the Bot API JSON
                # envelope — response.json() would raise JSONDecodeError.
                self.html_error_sends -= 1
                return HTMLResponse(
                    status_code=502, content="<html><body>502 Bad Gateway</body></html>"
                )
            if self.reject_all_sends > 0:
                self.reject_all_sends -= 1
                return JSONResponse(
                    status_code=400, content={"ok": False, "description": "rejected"}
                )
            if self.reject_html_sends > 0 and params.get("parse_mode") == "HTML":
                self.reject_html_sends -= 1
                return JSONResponse(
                    status_code=400,
                    content={"ok": False, "description": "can't parse entities"},
                )
            self._next_message_id += 1
            return JSONResponse(
                content={"ok": True, "result": {"message_id": self._next_message_id}}
            )
        if method == "getFile":
            file_id = params.get("file_id")
            return JSONResponse(
                content={
                    "ok": True,
                    "result": {"file_id": file_id, "file_path": f"downloads/{file_id}.bin"},
                }
            )
        return JSONResponse(content={"ok": True, "result": {}})

    def calls_for(self, method: str) -> list[dict[str, Any]]:
        return [params for m, params in self.calls if m == method]


class FakeSeaTalk:
    """Scriptable in-process SeaTalk Open API: counts token grants, records
    single_chat sends, and pops scripted (status, payload) failures in order."""

    def __init__(self) -> None:
        self.token_calls = 0
        self.single_chat_calls: list[tuple[dict[str, Any], str]] = []  # (body, Authorization)
        self.group_chat_calls: list[tuple[dict[str, Any], str]] = []  # (body, Authorization)
        self.typing_calls: list[dict[str, Any]] = []
        self.group_typing_calls: list[dict[str, Any]] = []
        self.scripted: list[tuple[int, dict[str, Any]]] = []  # popped per single/group_chat call
        self.html_error_sends = 0  # answer single_chat with a non-JSON HTML body N times
        self._next_message_id = 0
        # -- thread fetch (Task 5) --
        self.thread_calls: list[dict[str, Any]] = []  # query params, one per /get_thread... GET
        self.thread_response: dict[str, Any] = {"code": 0, "thread_messages": []}
        # -- message streaming (FR-037) --
        # (surface, body) per call, where surface is "single_chat"/"group_chat".
        self.init_stream_calls: list[tuple[str, dict[str, Any]]] = []
        self.update_stream_calls: list[tuple[str, dict[str, Any]]] = []
        self.stream_init_fails = 0  # reject init_stream N times
        self.fail_stream_update_at: int | None = None  # reject the Nth update (1-based)
        self._live_streams: set[str] = set()  # ids that are still open
        self._next_stream_id = 0
        self.file_downloads: list[str] = []  # file ids fetched, one per media GET
        self.file_bytes = b"\x89PNG\r\n\x1a\nFAKE"  # served for any file download
        self.app = FastAPI()
        self.app.post("/auth/app_access_token")(self._token)
        self.app.post("/messaging/v2/single_chat")(self._single_chat)
        self.app.post("/messaging/v2/group_chat")(self._group_chat)
        self.app.post("/messaging/v2/single_chat_typing")(self._typing)
        self.app.post("/messaging/v2/group_chat_typing")(self._group_typing)
        # -- message streaming (FR-037) --
        self.app.post("/messaging/v2/{surface}/init_stream")(self._init_stream)
        self.app.post("/messaging/v2/{surface}/update_stream")(self._update_stream)
        self.app.get("/messaging/v2/group_chat/get_thread_by_thread_id")(self._thread)
        self.app.get("/messaging/v2/file/{file_id}")(self._serve_file)

    async def _serve_file(self, file_id: str) -> Response:
        self.file_downloads.append(file_id)
        return Response(content=self.file_bytes, media_type="image/png")

    async def _token(self, request: Request) -> JSONResponse:
        await request.json()
        self.token_calls += 1
        return JSONResponse(
            content={"code": 0, "app_access_token": f"tok-{self.token_calls}", "expire": 7200}
        )

    async def _single_chat(self, request: Request) -> JSONResponse:
        body: dict[str, Any] = await request.json()
        self.single_chat_calls.append((body, request.headers.get("Authorization", "")))
        if self.html_error_sends > 0:
            # A gateway returns a 502 HTML page, not the Open API JSON
            # envelope — response.json() would raise JSONDecodeError.
            self.html_error_sends -= 1
            return HTMLResponse(
                status_code=502, content="<html><body>502 Bad Gateway</body></html>"
            )
        if self.scripted:
            status, payload = self.scripted.pop(0)
            return JSONResponse(status_code=status, content=payload)
        self._next_message_id += 1
        return JSONResponse(content={"code": 0, "message_id": f"m{self._next_message_id}"})

    async def _group_chat(self, request: Request) -> JSONResponse:
        body: dict[str, Any] = await request.json()
        self.group_chat_calls.append((body, request.headers.get("Authorization", "")))
        if self.html_error_sends > 0:
            self.html_error_sends -= 1
            return HTMLResponse(
                status_code=502, content="<html><body>502 Bad Gateway</body></html>"
            )
        if self.scripted:
            status, payload = self.scripted.pop(0)
            return JSONResponse(status_code=status, content=payload)
        self._next_message_id += 1
        return JSONResponse(content={"code": 0, "message_id": f"m{self._next_message_id}"})

    async def _group_typing(self, request: Request) -> JSONResponse:
        self.group_typing_calls.append(await request.json())
        return JSONResponse({"code": 0})

    async def _typing(self, request: Request) -> JSONResponse:
        self.typing_calls.append(await request.json())
        return JSONResponse(content={"code": 0})

    async def _init_stream(self, surface: str, request: Request) -> JSONResponse:
        body: dict[str, Any] = await request.json()
        self.init_stream_calls.append((surface, body))
        if self.stream_init_fails > 0:
            self.stream_init_fails -= 1
            return JSONResponse(content={"code": 5, "message": "stream refused"})
        self._next_stream_id += 1
        stream_id = f"s{self._next_stream_id}"
        self._live_streams.add(stream_id)
        return JSONResponse(content={"code": 0, "stream_id": stream_id})

    async def _update_stream(self, surface: str, request: Request) -> JSONResponse:
        body: dict[str, Any] = await request.json()
        self.update_stream_calls.append((surface, body))
        stream_id = str(body.get("stream_id", ""))
        if stream_id not in self._live_streams:
            # The real platform rejects any request naming a stream that has
            # ended (finished, timed out, or errored) — never reusable.
            return JSONResponse(content={"code": 5, "message": "stream is not active"})
        if self.fail_stream_update_at == len(self.update_stream_calls):
            self._live_streams.discard(stream_id)  # an errored stream is terminated
            return JSONResponse(content={"code": 5, "message": "stream update rejected"})
        if body.get("finish"):
            self._live_streams.discard(stream_id)
        return JSONResponse(content={"code": 0})

    async def _thread(self, request: Request) -> JSONResponse:
        self.thread_calls.append(dict(request.query_params))
        return JSONResponse(content=self.thread_response)


def make_telegram_adapter(fake: FakeTelegram, *, poll_timeout: int = 1) -> TelegramAdapter:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=fake.app), base_url="http://fake")
    return TelegramAdapter(
        "tg", "BOT_TOKEN", client=client, base_url="http://fake", poll_timeout=poll_timeout
    )


def make_seatalk_adapter(fake: FakeSeaTalk, *, media_dir: Any = None) -> SeaTalkAdapter:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=fake.app), base_url="http://fake")
    return SeaTalkAdapter(
        "st", "app-1", "app-secret", client=client, base_url="http://fake", media_dir=media_dir
    )


@pytest.fixture
def fake_telegram() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def fake_seatalk() -> FakeSeaTalk:
    return FakeSeaTalk()
