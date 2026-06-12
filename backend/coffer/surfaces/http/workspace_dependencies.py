"""FastAPI dependency providers for the agent-workspace facets.

Split out of ``coffer.surfaces.http.dependencies`` (specs 004/005 amendment)
to keep that kind-agnostic module under its file-size budget. Same pattern:
the composition root calls the setters once on startup; routes Depends() on
the getters. Typed as Any to avoid kind-specific imports (Contract 6).
"""

from __future__ import annotations

from typing import Any

_agent_mcp_entry_service: Any | None = None
_agent_plugin_service: Any | None = None


def set_agent_mcp_entry_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _agent_mcp_entry_service
    _agent_mcp_entry_service = svc


def get_agent_mcp_entry_service() -> Any:
    """FastAPI Depends() target — actual type is AgentMcpEntryService."""
    if _agent_mcp_entry_service is None:
        raise RuntimeError("agent MCP-entry service not initialised")
    return _agent_mcp_entry_service


def set_agent_plugin_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _agent_plugin_service
    _agent_plugin_service = svc


def get_agent_plugin_service() -> Any:
    """FastAPI Depends() target — actual type is AgentPluginService."""
    if _agent_plugin_service is None:
        raise RuntimeError("agent plugin service not initialised")
    return _agent_plugin_service
