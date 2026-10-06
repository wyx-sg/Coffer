"""A minimal MCP client over the target's ``/mcp`` endpoint, written by hand.

The official SDK hides the wire; these cases need it — exact envelopes, missing
headers, request ids reused across sessions, a notification stream read line
by line. Every exchange lands in the run's transcript through the daemon client.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from e2e.installed._common.http import DaemonClient, Reply

PROTOCOL = "2025-06-18"
CLIENT_INFO = {"name": "qa-installed-acceptance", "version": "1.0"}

Responder = Callable[[dict[str, Any]], dict[str, Any] | None]


def ok(reply: Reply) -> bool:
    """A JSON-RPC result that is not an in-band tool error."""
    result = reply.json.get("result")
    return isinstance(result, dict) and not result.get("isError")


def in_band_error(reply: Reply) -> bool:
    result = reply.json.get("result")
    return isinstance(result, dict) and result.get("isError") is True


def code(reply: Reply) -> int | None:
    error = reply.json.get("error")
    return error.get("code") if isinstance(error, dict) else None


def text_of(reply: Reply) -> str:
    content = (reply.json.get("result") or {}).get("content") or []
    return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))


def structured(reply: Reply) -> dict[str, Any]:
    value = (reply.json.get("result") or {}).get("structuredContent")
    return value if isinstance(value, dict) else {}


class Wire:
    def __init__(self, client: DaemonClient) -> None:
        self.client = client

    async def post(
        self,
        body: Any,
        sid: str | None = None,
        headers: Mapping[str, str | None] | None = None,
        timeout: float = 15,
        content: str | None = None,
    ) -> Reply:
        sent: dict[str, str | None] = {"MCP-Protocol-Version": PROTOCOL}
        if sid:
            sent["Mcp-Session-Id"] = sid
        sent.update(headers or {})
        return await self.client.request(
            "POST", "/mcp", body, headers=sent, timeout=timeout, content=content
        )

    async def rpc(
        self,
        method: str,
        params: Any = None,
        sid: str | None = None,
        rid: Any = 1,
        headers: Mapping[str, str | None] | None = None,
        timeout: float = 15,
    ) -> Reply:
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if rid is not None:
            body["id"] = rid
        if params is not None:
            body["params"] = params
        return await self.post(body, sid, headers, timeout)

    async def notify(self, method: str, params: Any, sid: str | None) -> Reply:
        return await self.rpc(method, params, sid, rid=None)

    async def initialize(
        self,
        agent: str | None = None,
        caps: dict[str, Any] | None = None,
        version: str = PROTOCOL,
        meta: dict[str, Any] | None = None,
        sid: str | None = None,
    ) -> tuple[str, Reply]:
        """``initialize`` + ``notifications/initialized``; returns the new session id."""
        params: dict[str, Any] = {
            "protocolVersion": version,
            "capabilities": caps or {},
            "clientInfo": CLIENT_INFO,
        }
        if meta is not None:
            params["_meta"] = meta
        elif agent is not None:
            params["_meta"] = {"coffer/agent-uid": agent}
        reply = await self.rpc("initialize", params, sid=sid)
        session = sid or reply.headers.get("mcp-session-id") or ""
        if session and reply.status == 200 and "result" in reply.json:
            await self.notify("notifications/initialized", {}, session)
        return session, reply

    async def call(
        self,
        sid: str,
        name: str,
        arguments: dict[str, Any] | None = None,
        rid: Any = 10,
        meta: dict[str, Any] | None = None,
        timeout: float = 15,
    ) -> Reply:
        params: dict[str, Any] = {"name": name, "arguments": arguments or {}}
        if meta:
            params["_meta"] = meta
        return await self.rpc("tools/call", params, sid, rid=rid, timeout=timeout)

    async def tool_names(self, sid: str) -> list[str]:
        reply = await self.rpc("tools/list", {}, sid)
        return [t["name"] for t in (reply.json.get("result") or {}).get("tools", [])]

    async def tools(self, sid: str) -> list[dict[str, Any]]:
        reply = await self.rpc("tools/list", {}, sid)
        return list((reply.json.get("result") or {}).get("tools", []))

    async def search(self, sid: str, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        reply = await self.call(sid, "coffer__search_tools", {"query": query, "top_k": top_k})
        return list(structured(reply).get("tools", []))


class EventStream:
    """A session's notification stream (``GET /mcp``), read in the background.

    With a ``responder``, every server-initiated request on the stream
    (``sampling/createMessage``, ``roots/list``) is answered by POSTing the
    responder's result back on the same session, as a client would.
    """

    def __init__(
        self, wire: Wire, sid: str, responder: Responder | None = None, seconds: float = 30
    ) -> None:
        self.wire, self.sid, self.responder, self.seconds = wire, sid, responder, seconds
        self.messages: list[dict[str, Any]] = []
        self.status: int | None = None
        self._ready = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def requests(self, method: str) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("method") == method and "id" in m]

    def methods(self) -> list[str]:
        return [m.get("method", "") for m in self.messages]

    async def __aenter__(self) -> EventStream:
        self._task = asyncio.create_task(self._read())
        await asyncio.wait_for(self._ready.wait(), 10)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task

    async def settle(self, seconds: float = 0.5) -> None:
        await asyncio.sleep(seconds)

    async def _read(self) -> None:
        headers: dict[str, str | None] = {
            "Mcp-Session-Id": self.sid,
            "Accept": "text/event-stream",
            "MCP-Protocol-Version": PROTOCOL,
        }
        try:
            async with self.wire.client.stream(
                "GET", "/mcp", headers=headers, timeout=self.seconds
            ) as response:
                self.status = response.status_code
                self._ready.set()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        await self._take(json.loads(line[6:]))
        finally:
            self._ready.set()

    async def _take(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        self.wire.client.log({"direction": "stream-event", "session": self.sid, "event": message})
        if self.responder and "id" in message and "method" in message:
            result = self.responder(message)
            if result is not None:
                answer = {"jsonrpc": "2.0", "id": message["id"], "result": result}
                await self.wire.post(answer, self.sid)


def answering(sample_text: str, root_uri: str) -> Responder:
    """A client that answers sampling with ``sample_text`` and roots with ``root_uri``."""

    def respond(message: dict[str, Any]) -> dict[str, Any] | None:
        if message.get("method") == "sampling/createMessage":
            return {
                "model": "qa-synthetic-no-provider",
                "role": "assistant",
                "content": {"type": "text", "text": sample_text},
            }
        if message.get("method") == "roots/list":
            return {"roots": [{"uri": root_uri, "name": "qa root"}]}
        return None

    return respond


async def gather_ok(*calls: Awaitable[Reply]) -> list[Reply]:
    return list(await asyncio.gather(*calls))
