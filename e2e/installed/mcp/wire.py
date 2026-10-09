"""A minimal hand-written MCP client over the target's ``/mcp`` endpoint.

The cases speak through the official SDK; this is only for the setup (one
session's ``tools/list`` makes the target save each server's tool list) and
for reading a result's fields without the SDK's models. Every exchange lands in
the run's transcript through the daemon client.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from e2e.installed._common.http import DaemonClient, Reply

PROTOCOL = "2025-06-18"
CLIENT_INFO = {"name": "qa-installed-acceptance", "version": "1.0"}


def ok(reply: Reply) -> bool:
    """A JSON-RPC result that is not an in-band tool error."""
    result = reply.json.get("result")
    return isinstance(result, dict) and not result.get("isError")


def text_of(reply: Reply) -> str:
    content = (reply.json.get("result") or {}).get("content") or []
    return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))


def structured(reply: Reply) -> dict[str, Any]:
    value = (reply.json.get("result") or {}).get("structuredContent")
    return value if isinstance(value, dict) else {}


class Wire:
    def __init__(self, client: DaemonClient) -> None:
        self.client = client

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
        sent: dict[str, str | None] = {"MCP-Protocol-Version": PROTOCOL}
        if sid:
            sent["Mcp-Session-Id"] = sid
        sent.update(headers or {})
        return await self.client.request("POST", "/mcp", body, headers=sent, timeout=timeout)

    async def initialize(self, agent: str | None = None) -> str:
        """``initialize`` + ``notifications/initialized``; returns the new session id."""
        params: dict[str, Any] = {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        }
        if agent is not None:
            params["_meta"] = {"coffer/agent-uid": agent}
        reply = await self.rpc("initialize", params)
        session = reply.headers.get("mcp-session-id") or ""
        if session and reply.status == 200 and "result" in reply.json:
            await self.rpc("notifications/initialized", {}, session, rid=None)
        return session

    async def call(
        self, sid: str, name: str, arguments: dict[str, Any] | None = None, timeout: float = 15
    ) -> Reply:
        params = {"name": name, "arguments": arguments or {}}
        return await self.rpc("tools/call", params, sid, rid=10, timeout=timeout)

    async def tool_names(self, sid: str) -> list[str]:
        reply = await self.rpc("tools/list", {}, sid)
        return [t["name"] for t in (reply.json.get("result") or {}).get("tools", [])]
