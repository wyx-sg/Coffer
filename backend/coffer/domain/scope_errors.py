"""Per-agent MCP scoping errors (ADR-026).

Kind-agnostic: split out of ``coffer.domain.errors`` for the file-size limit.
Lives here (not under ``domain/agent/`` or ``domain/mcp/``) so both the agent
scope service and the mcp gateway can import it without crossing kind isolation.
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class AgentMcpServerNotInScope(CofferError):  # noqa: N818
    """A gateway session targeted an MCP server outside the agent's scope.

    Raised when a ``selected``-mode agent directly calls a tool / reads a
    resource / gets a prompt on a server that is not in its allowlist. The
    gateway turns this into a JSON-RPC error instead of invoking the upstream.
    """

    code = "MCP_SERVER_OUT_OF_SCOPE"

    def __init__(self, server_name: str) -> None:
        super().__init__(f"server is not in this agent's scope: {server_name}")
        self.server_name = server_name


class AgentMcpScopeServerUnknown(CofferError):  # noqa: N818
    """An agent's selected scope named an MCP server that is not registered."""

    code = "MCP_SCOPE_SERVER_UNKNOWN"

    def __init__(self, server_name: str) -> None:
        super().__init__(f"unknown MCP server in scope: {server_name}")
        self.server_name = server_name
