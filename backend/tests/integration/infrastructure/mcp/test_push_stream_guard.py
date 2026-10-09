"""The push-stream guard stops the SDK reopening a GET stream the upstream closes at once.

Postman's hosted MCP server answered the post-initialize ``GET /mcp`` with 200
and closed the body straight away; the SDK reopened it every second for the
life of the session (TODO O-8). These tests drive the real SDK client against
an in-process upstream that does the same, through ``httpx2.MockTransport``.
"""

from __future__ import annotations

import json

import anyio
import httpx2
import mcp.client.streamable_http as sdk_streamable_http
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from coffer.infrastructure.mcp.push_stream_guard import (
    GuardedAsyncClient,
    PushStreamGuard,
    is_push_stream_request,
)

_URL = "http://upstream.test/mcp"


class _EmptyBody(httpx2.AsyncByteStream):
    """A streamed body that ends at once, as a network response would deliver it.

    (``content=b""`` would be read eagerly into the response, so the client
    would never iterate or close a stream at all.)
    """

    async def __aiter__(self):  # type: ignore[override]
        return
        yield b""


class _ClosesPushStreamAtOnce:
    """A minimal streamable-HTTP upstream whose push stream ends as soon as it opens."""

    def __init__(self) -> None:
        self.push_stream_opens = 0

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if request.method == "GET":
            self.push_stream_opens += 1
            return httpx2.Response(
                200, headers={"content-type": "text/event-stream"}, stream=_EmptyBody()
            )
        if request.method == "DELETE":
            return httpx2.Response(200)
        message = json.loads(request.content)
        if message.get("method") == "initialize":
            result = {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "closes-at-once", "version": "1"},
            }
            return httpx2.Response(
                200,
                headers={"content-type": "application/json", "mcp-session-id": "s-1"},
                json={"jsonrpc": "2.0", "id": message["id"], "result": result},
            )
        return httpx2.Response(202)


@pytest.mark.asyncio
async def test_push_stream_closed_at_once_is_not_reopened_forever(monkeypatch) -> None:
    # The SDK waits a second between reopens; shorten it so the test is quick.
    monkeypatch.setattr(sdk_streamable_http, "DEFAULT_RECONNECTION_DELAY_MS", 10)
    upstream = _ClosesPushStreamAtOnce()
    guard = PushStreamGuard("postman")
    client = GuardedAsyncClient(guard=guard, transport=httpx2.MockTransport(upstream))

    async with (
        client,
        streamable_http_client(_URL, http_client=client) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        with anyio.fail_after(5):
            while not guard.disabled:
                await anyio.sleep(0.01)
        opens_when_disabled = upstream.push_stream_opens
        # Ample time for dozens of reopens at the shortened delay.
        await anyio.sleep(0.5)

    assert opens_when_disabled == 3
    assert upstream.push_stream_opens == opens_when_disabled


def test_a_long_lived_stream_resets_the_count() -> None:
    now = [0.0]
    guard = PushStreamGuard("pushes-normally", clock=lambda: now[0])

    for _ in range(2):
        guard.closed(guard.opened())  # two streams that closed at once
    opened = guard.opened()
    now[0] += 60.0  # one that stayed open a minute
    guard.closed(opened)
    for _ in range(2):
        guard.closed(guard.opened())

    assert not guard.disabled
    guard.closed(guard.opened())
    assert guard.disabled


def test_only_event_stream_gets_are_push_streams() -> None:
    sse = {"accept": "text/event-stream"}
    assert is_push_stream_request(httpx2.Request("GET", _URL, headers=sse))
    assert not is_push_stream_request(httpx2.Request("POST", _URL, headers=sse))
    assert not is_push_stream_request(httpx2.Request("GET", _URL))
