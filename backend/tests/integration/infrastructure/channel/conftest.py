"""Shared in-process platform fakes for channel transport tests (spec 009).

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
from fastapi import FastAPI, Request
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
        self.html_error_sends = 0  # answer sendMessage with a non-JSON HTML body N times
        self._next_message_id = 100
        self.app = FastAPI()
        self.app.post("/bot{token}/{method}")(self._handle)

    async def _handle(self, token: str, method: str, request: Request) -> JSONResponse:
        params: dict[str, Any] = await request.json()
        self.calls.append((method, params))
        if method == "getUpdates":
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
        return JSONResponse(content={"ok": True, "result": {}})

    def calls_for(self, method: str) -> list[dict[str, Any]]:
        return [params for m, params in self.calls if m == method]


class FakeSeaTalk:
    """Scriptable in-process SeaTalk Open API: counts token grants, records
    single_chat sends, and pops scripted (status, payload) failures in order."""

    def __init__(self) -> None:
        self.token_calls = 0
        self.single_chat_calls: list[tuple[dict[str, Any], str]] = []  # (body, Authorization)
        self.typing_calls: list[dict[str, Any]] = []
        self.scripted: list[tuple[int, dict[str, Any]]] = []  # popped per single_chat call
        self.html_error_sends = 0  # answer single_chat with a non-JSON HTML body N times
        self._next_message_id = 0
        self.app = FastAPI()
        self.app.post("/auth/app_access_token")(self._token)
        self.app.post("/messaging/v2/single_chat")(self._single_chat)
        self.app.post("/messaging/v2/single_chat_typing")(self._typing)

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

    async def _typing(self, request: Request) -> JSONResponse:
        self.typing_calls.append(await request.json())
        return JSONResponse(content={"code": 0})


def make_telegram_adapter(fake: FakeTelegram, *, poll_timeout: int = 1) -> TelegramAdapter:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=fake.app), base_url="http://fake")
    return TelegramAdapter(
        "tg", "BOT_TOKEN", client=client, base_url="http://fake", poll_timeout=poll_timeout
    )


def make_seatalk_adapter(fake: FakeSeaTalk) -> SeaTalkAdapter:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=fake.app), base_url="http://fake")
    return SeaTalkAdapter("st", "app-1", "app-secret", client=client, base_url="http://fake")


@pytest.fixture
def fake_telegram() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def fake_seatalk() -> FakeSeaTalk:
    return FakeSeaTalk()
