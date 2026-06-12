"""GatewayToolProvider — ToolGateway implementation over an MCPGatewaySession.

This is the infrastructure glue that connects the agent-chat application layer
(which depends on the ``ToolGateway`` port) to Coffer's in-process MCP gateway
(``application.mcp.gateway.MCPGatewaySession``).

Architecture
------------
One ``MCPGatewaySession`` (session-id ``coffer-builtin-agent``) is constructed
at wiring time by the composition root and passed here.  Both ``list_tools``
and ``call_tool`` are thin wrappers that forward to
``session.handle_request("tools/list" | "tools/call", ...)``.

Import legality
---------------
``infrastructure.chat``  →  ``application.mcp.gateway`` is infrastructure →
application, which is the standard direction and does NOT violate any import
contracts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from coffer.application.chat.ports import ToolSpec

if TYPE_CHECKING:
    from coffer.application.mcp.gateway import MCPGatewaySession

log = logging.getLogger(__name__)


class GatewayToolProvider:
    """``ToolGateway`` backed by an in-process ``MCPGatewaySession``.

    Parameters
    ----------
    session:
        The long-lived gateway session constructed by the composition root.
        It is shared across all turns; the session is stateless with respect
        to individual turns (no per-turn state is held).
    """

    def __init__(self, session: MCPGatewaySession) -> None:
        self._session = session

    async def list_tools(self) -> list[ToolSpec]:
        """Return all tools exposed by the gateway as ``ToolSpec`` objects."""
        result: dict[str, Any] = await self._session.handle_request("tools/list", {})
        raw_tools: list[dict[str, Any]] = result.get("tools") or []
        specs: list[ToolSpec] = []
        for t in raw_tools:
            name = str(t.get("name") or "")
            description = str(t.get("description") or "")
            # The MCP protocol uses ``inputSchema``; fall back to ``input_schema``
            # for forward-compat / internal built-in tool representations.
            input_schema: dict[str, Any] = t.get("inputSchema") or t.get("input_schema") or {}
            if name:
                specs.append(
                    ToolSpec(name=name, description=description, input_schema=input_schema)
                )
        return specs

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Call a single tool by name and return its result dict."""
        try:
            result: Any = await self._session.handle_request(
                "tools/call",
                {"name": name, "arguments": args},
            )
        except Exception:
            log.warning("gateway call_tool failed: tool=%r", name, exc_info=True)
            raise
        # Gateway may return None or a non-dict on error; normalise to dict.
        if isinstance(result, dict):
            return result
        return {"result": result}


__all__ = ["GatewayToolProvider"]
