"""What a test client sends to open an MCP session on ``/mcp``.

The gateway refuses an ``initialize`` without the three fields MCP requires
(spec mcp-gateway "Answer every MCP message by the JSON-RPC rules"), so every
test that handshakes by hand starts from these params.
"""

from __future__ import annotations

from typing import Any

PROTOCOL_VERSION = "2025-06-18"


def init_params(
    meta: dict[str, Any] | None = None, capabilities: dict[str, Any] | None = None
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": capabilities or {},
        "clientInfo": {"name": "coffer-tests", "version": "1"},
    }
    if meta:
        params["_meta"] = meta
    return params


#: The plain handshake: no identity, no capabilities.
INIT_PARAMS: dict[str, Any] = init_params()
