"""MCP requests refused with a specific JSON-RPC error code.

Spec mcp-gateway "Answer every MCP message by the JSON-RPC rules". These are
protocol answers on the ``/mcp`` wire, not REST errors, so they are not
``CofferError``s and carry no HTTP status: the gateway's HTTP surface writes
``code`` and ``message`` into the JSON-RPC ``error`` object as they are.
"""

from __future__ import annotations

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcError(Exception):
    """A request answered with a JSON-RPC error; ``message`` is Coffer's own text."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def invalid_params(message: str) -> JsonRpcError:
    return JsonRpcError(INVALID_PARAMS, message)


def unknown_capability(label: str, name: object) -> JsonRpcError:
    """A tool, resource or prompt no visible server offers by that name (MCP
    answers an unknown tool with ``-32602``)."""
    return JsonRpcError(INVALID_PARAMS, f"unknown {label}: {name!r}")


__all__ = [
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "JsonRpcError",
    "invalid_params",
    "unknown_capability",
]
