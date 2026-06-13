"""Unit tests for the Codex app-server JSON-RPC-over-stdio client (T1).

Pure tests — no subprocess, no network. A fake reader feeds canned
``\\n``-delimited JSON lines and a fake writer captures the outbound NDJSON, so
the inbound dispatch loop (response correlation, server→client request routing
+ write-back, notification routing, malformed-line tolerance) is exercised
without a real ``codex`` binary.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcClient


class FakeReader:
    """A ``StreamReader``-like seam: yields pre-seeded lines, then EOF.

    New lines can be pushed mid-test (e.g. a response that only arrives after
    the client has written its request) via :meth:`feed`.
    """

    def __init__(self, lines: list[bytes] | None = None) -> None:
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        for line in lines or []:
            self._queue.put_nowait(line)

    def feed(self, obj: Any) -> None:
        self._queue.put_nowait((json.dumps(obj) + "\n").encode("utf-8"))

    def feed_raw(self, raw: bytes) -> None:
        self._queue.put_nowait(raw)

    def close(self) -> None:
        self._queue.put_nowait(None)

    async def readline(self) -> bytes:
        item = await self._queue.get()
        return b"" if item is None else item


class FakeWriter:
    """A ``StreamWriter``-like seam capturing every written frame as a dict."""

    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        text = data.decode("utf-8")
        assert text.endswith("\n"), "frames must be newline-terminated"
        for line in text.splitlines():
            if line:
                self.frames.append(json.loads(line))

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


async def test_request_correlates_response_by_id() -> None:
    reader = FakeReader()
    writer = FakeWriter()
    client = CodexRpcClient(reader, writer)
    client.start()

    async def respond_later() -> None:
        # Wait until the request frame is written, then answer it by id.
        for _ in range(100):
            if writer.frames:
                break
            await asyncio.sleep(0)
        sent = writer.frames[-1]
        reader.feed({"id": sent["id"], "result": {"ok": True, "echo": sent["params"]}})

    responder = asyncio.create_task(respond_later())
    result = await asyncio.wait_for(client.request("initialize", {"a": 1}), timeout=1.0)
    await responder

    assert result == {"ok": True, "echo": {"a": 1}}
    # Framing: the request was a single object with method/params and an id.
    sent = writer.frames[0]
    assert sent["method"] == "initialize"
    assert sent["params"] == {"a": 1}
    assert "id" in sent
    await client.close()


async def test_server_request_routed_to_handler_and_written_back() -> None:
    reader = FakeReader()
    writer = FakeWriter()
    client = CodexRpcClient(reader, writer)

    seen: list[dict[str, Any]] = []

    async def handler(params: dict[str, Any]) -> dict[str, Any]:
        seen.append(params)
        return {"decision": "accept"}

    client.on_request("item/commandExecution/requestApproval", handler)
    client.start()

    reader.feed(
        {
            "id": 42,
            "method": "item/commandExecution/requestApproval",
            "params": {"itemId": "i1", "command": "rm -rf /"},
        }
    )

    # Wait for the write-back.
    for _ in range(100):
        if writer.frames:
            break
        await asyncio.sleep(0)

    assert seen == [{"itemId": "i1", "command": "rm -rf /"}]
    back = writer.frames[-1]
    assert back["id"] == 42
    assert back["result"] == {"decision": "accept"}
    await client.close()


async def test_notifications_routed_to_async_iterator() -> None:
    reader = FakeReader()
    writer = FakeWriter()
    client = CodexRpcClient(reader, writer)
    client.start()

    reader.feed({"method": "thread/started", "params": {"thread": {"id": "t1"}}})
    reader.feed({"method": "item/agentMessage/delta", "params": {"delta": "hi"}})

    notes = client.notifications()
    first = await asyncio.wait_for(notes.__anext__(), timeout=1.0)
    second = await asyncio.wait_for(notes.__anext__(), timeout=1.0)

    assert first == ("thread/started", {"thread": {"id": "t1"}})
    assert second == ("item/agentMessage/delta", {"delta": "hi"})
    await client.close()


async def test_malformed_lines_are_ignored() -> None:
    reader = FakeReader()
    writer = FakeWriter()
    client = CodexRpcClient(reader, writer)
    client.start()

    reader.feed_raw(b"not json at all\n")
    reader.feed_raw(b"\n")  # blank line
    reader.feed_raw(b"{ broken json\n")
    reader.feed({"method": "thread/started", "params": {"ok": 1}})

    notes = client.notifications()
    note = await asyncio.wait_for(notes.__anext__(), timeout=1.0)
    assert note == ("thread/started", {"ok": 1})
    await client.close()


async def test_interleaved_response_request_notification() -> None:
    """A single inbound loop must demux all three frame kinds in arrival order."""
    reader = FakeReader()
    writer = FakeWriter()
    client = CodexRpcClient(reader, writer)

    async def handler(_params: dict[str, Any]) -> dict[str, Any]:
        return {"decision": "decline"}

    client.on_request("approve", handler)
    client.start()

    # Issue a request; its response is interleaved with a notification and a
    # server-request below.
    req = asyncio.create_task(client.request("turn/start", {"x": 1}))
    for _ in range(100):
        if writer.frames:
            break
        await asyncio.sleep(0)
    req_id = writer.frames[-1]["id"]

    reader.feed({"method": "thread/started", "params": {"n": 1}})
    reader.feed({"id": 7, "method": "approve", "params": {}})
    reader.feed({"id": req_id, "result": {"turn": {"id": "x"}}})

    result = await asyncio.wait_for(req, timeout=1.0)
    assert result == {"turn": {"id": "x"}}

    note = await asyncio.wait_for(client.notifications().__anext__(), timeout=1.0)
    assert note == ("thread/started", {"n": 1})

    # The server-request write-back is present.
    write_backs = [f for f in writer.frames if f.get("id") == 7 and "result" in f]
    assert write_backs and write_backs[0]["result"] == {"decision": "decline"}
    await client.close()


async def test_eof_event_set_on_natural_eof() -> None:
    """``rpc.eof`` fires when the reader signals natural EOF (empty bytes)."""
    reader = FakeReader()
    writer = FakeWriter()
    client = CodexRpcClient(reader, writer)
    client.start()

    # Sanity: not yet set while the read loop is waiting.
    assert not client.eof.is_set()

    # Feed EOF.
    reader.close()
    await asyncio.wait_for(client.eof.wait(), timeout=1.0)
    assert client.eof.is_set()


async def test_eof_event_set_on_close_without_start() -> None:
    """``rpc.eof`` fires after ``close()`` even when ``start()`` was never called."""
    reader = FakeReader()
    writer = FakeWriter()
    client = CodexRpcClient(reader, writer)
    # Deliberately do NOT call start().
    await client.close()
    assert client.eof.is_set()


async def test_eof_event_set_on_close_while_running() -> None:
    """``rpc.eof`` fires when ``close()`` cancels a running read loop."""
    reader = FakeReader()
    writer = FakeWriter()
    client = CodexRpcClient(reader, writer)
    client.start()
    # Loop is blocked waiting for a line — close() must cancel it and set eof.
    await client.close()
    assert client.eof.is_set()
