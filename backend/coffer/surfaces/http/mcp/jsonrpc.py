"""JSON-RPC rules of the ``/mcp`` endpoint: what a message must look like, and
which error code answers which failure.

Spec mcp-gateway "Answer every MCP message by the JSON-RPC rules". Everything
here is checked before the session or an upstream is touched, so a malformed
message never reaches application code and never becomes an HTTP 500.
"""

from __future__ import annotations

from typing import Any

from mcp import MCPError

from coffer.application.mcp.gateway_instructions import PROTOCOL_VERSION
from coffer.domain.errors import CofferError
from coffer.domain.mcp.jsonrpc_errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    JsonRpcError,
)

#: The requests the gateway answers. ``initialize`` and ``ping`` are answered by
#: the surface and the session; the rest are dispatched by the session.
REQUEST_METHODS = frozenset(
    {
        "initialize",
        "ping",
        "tools/list",
        "tools/call",
        "resources/list",
        "resources/read",
        "prompts/list",
        "prompts/get",
    }
)

#: The MCP versions the gateway speaks; a client asking for another is offered
#: this one at ``initialize`` (MCP "Version negotiation").
SUPPORTED_PROTOCOL_VERSIONS = frozenset({PROTOCOL_VERSION})

#: Coffer's own "this capability is switched off / out of scope" answer.
TOOL_DISABLED = -32000


def error_body(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _valid_id(value: object) -> bool:
    # MCP: a request id is a string or an integer, never null; bool is not an int here.
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def check_envelope(envelope: object) -> tuple[Any, JsonRpcError | None]:
    """The id to answer with and, when the message is malformed, why.

    The id is echoed only when it is itself valid; otherwise the answer carries
    ``null`` as JSON-RPC requires.
    """
    if not isinstance(envelope, dict):
        return None, JsonRpcError(INVALID_REQUEST, "a message must be a JSON object")
    has_id = "id" in envelope
    req_id = envelope.get("id")
    answer_id = req_id if _valid_id(req_id) else None
    if envelope.get("jsonrpc") != "2.0":
        return answer_id, JsonRpcError(INVALID_REQUEST, 'jsonrpc must be "2.0"')
    if has_id and not _valid_id(req_id):
        return None, JsonRpcError(INVALID_REQUEST, "id must be a string or an integer")
    method = envelope.get("method")
    if "method" in envelope and not isinstance(method, str):
        return answer_id, JsonRpcError(INVALID_REQUEST, "method must be a string")
    if method is None and not ({"result", "error"} & envelope.keys()):
        return answer_id, JsonRpcError(INVALID_REQUEST, "missing method")
    if "params" in envelope and not isinstance(envelope["params"], dict):
        return answer_id, JsonRpcError(INVALID_PARAMS, "params must be an object")
    return answer_id, None


def _require(params: dict[str, Any], key: str, kind: type, *, optional: bool = False) -> None:
    if key not in params:
        if optional:
            return
        raise JsonRpcError(INVALID_PARAMS, f"params.{key} is required")
    value = params[key]
    if not isinstance(value, kind) or (kind is str and not optional and value == ""):
        raise JsonRpcError(INVALID_PARAMS, f"params.{key} must be a {_KIND_NAMES[kind]}")


_KIND_NAMES: dict[type, str] = {str: "non-empty string", dict: "object"}


def check_params(method: str, params: dict[str, Any]) -> None:
    """Refuse the params a method cannot work with (``-32602``)."""
    if "_meta" in params and not isinstance(params["_meta"], dict):
        raise JsonRpcError(INVALID_PARAMS, "params._meta must be an object")
    if method == "initialize":
        _require(params, "protocolVersion", str)
        _require(params, "capabilities", dict)
        _require(params, "clientInfo", dict)
        info = params["clientInfo"]
        if not isinstance(info.get("name"), str) or not isinstance(info.get("version"), str):
            raise JsonRpcError(INVALID_PARAMS, "params.clientInfo needs a name and a version")
    elif method in ("tools/call", "prompts/get"):
        _require(params, "name", str)
        _require(params, "arguments", dict, optional=True)
    elif method == "resources/read":
        _require(params, "uri", str)
    elif method.endswith("/list") and "cursor" in params:
        _require(params, "cursor", str)


def error_for(exc: BaseException) -> tuple[int, str]:
    """The JSON-RPC code and message a failed request is answered with.

    An upstream's own JSON-RPC error keeps its code, so a client can tell
    "wrong arguments" from "server broke"; its message is not relayed (an
    upstream's text can echo a credential — spec secret "Hold plaintext only in
    memory at the moment of use"). ``-32000`` is not relayed either: the SDK
    uses it for a dropped connection and Coffer for a disabled tool.
    """
    if isinstance(exc, JsonRpcError):
        return exc.code, exc.message
    if isinstance(exc, CofferError):
        return (TOOL_DISABLED if exc.code == "TOOL_DISABLED" else INTERNAL_ERROR), str(exc)
    if isinstance(exc, MCPError):
        code = exc.code
        if isinstance(code, int) and code != TOOL_DISABLED:
            return code, f"the upstream server answered with JSON-RPC error {code}"
    return INTERNAL_ERROR, f"internal error: {type(exc).__name__}"


__all__ = [
    "METHOD_NOT_FOUND",
    "REQUEST_METHODS",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "TOOL_DISABLED",
    "check_envelope",
    "check_params",
    "error_body",
    "error_for",
]
