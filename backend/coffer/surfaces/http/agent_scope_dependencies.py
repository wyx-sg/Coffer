"""Per-agent MCP scope-service DI provider (ADR-026).

Split out of ``surfaces/http/dependencies.py`` for the file-size limit. Same
set/get singleton pattern as the other dependency providers in that module.
"""

from __future__ import annotations

from typing import Any

_agent_mcp_scope_service: Any | None = None


def set_agent_mcp_scope_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _agent_mcp_scope_service
    _agent_mcp_scope_service = svc


def get_agent_mcp_scope_service() -> Any:
    """FastAPI Depends() target — actual type is AgentMcpScopeService."""
    if _agent_mcp_scope_service is None:
        raise RuntimeError("agent MCP scope service not initialised")
    return _agent_mcp_scope_service
