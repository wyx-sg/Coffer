"""DI singleton for the MCP Registry search service (ADR-029).

Kept in the mcp-surface package (not the kind-agnostic ``dependencies`` module)
so the concrete service type can be referenced and the kind-agnostic core stays
under its size budget — mirrors ``agent_scope_dependencies`` for the agent kind.
"""

from __future__ import annotations

from coffer.application.mcp.registry_service import MCPRegistrySearchService

_mcp_registry_service: MCPRegistrySearchService | None = None


def set_mcp_registry_service(svc: MCPRegistrySearchService) -> None:
    """Called by the composition root once on startup."""
    global _mcp_registry_service
    _mcp_registry_service = svc


def get_mcp_registry_service() -> MCPRegistrySearchService:
    """FastAPI Depends() target."""
    if _mcp_registry_service is None:
        raise RuntimeError("MCP registry service not initialised")
    return _mcp_registry_service
