"""What an ``error`` invocation row says about the upstream's health.

The invocation log records one status vocabulary — ``ok`` / ``error`` /
``timeout`` / ``denied`` — and ``error`` covers two different things:

- the upstream ANSWERED, and the answer was a failure: a tool result carrying
  ``isError`` (the MCP spec's in-band tool error) or a well-formed JSON-RPC
  error. The connection is healthy; the tool failed.
- the upstream did NOT answer: it would not start, the transport died, the
  process crashed. That is what spec mcp-gateway "Route calls to the
  originating upstream" means by an unhealthy server.

Rather than widen the status vocabulary (which the web UI's filters and the
CLI's ``--status`` both name), the gateway writes a fixed, Coffer-authored
``error_message`` for the first kind, and :func:`is_upstream_answered` is how a
reader — the server-status route — tells them apart. Both markers are
Coffer-authored text, never upstream content (spec mcp-gateway "Record
invocations without content").
"""

from __future__ import annotations

from coffer.domain.mcp.capability import MCPInvocation

#: ``error_message`` of a tools/call whose result carried ``isError: True``.
INBAND_TOOL_ERROR = "upstream tool returned an error result (isError)"

#: ``error_message`` prefix of a request the upstream rejected with a
#: well-formed JSON-RPC error (anything but the SDK's CONNECTION_CLOSED, which
#: is a dead transport dressed as an error).
_ANSWERED_RPC_ERROR_PREFIX = "upstream answered with a JSON-RPC error"


def answered_rpc_error(code: int) -> str:
    """The recorded message for a JSON-RPC error the upstream returned.

    Only the numeric code is kept: the error's message text is upstream-authored
    and may echo secrets."""
    return f"{_ANSWERED_RPC_ERROR_PREFIX} (code {code})"


def is_upstream_answered(inv: MCPInvocation) -> bool:
    """True when this ``error`` row is the upstream answering with a failure —
    evidence the server is up, not that it is down."""
    msg = inv.error_message or ""
    return inv.status == "error" and (
        msg == INBAND_TOOL_ERROR or msg.startswith(_ANSWERED_RPC_ERROR_PREFIX)
    )
