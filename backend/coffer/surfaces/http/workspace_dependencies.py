"""FastAPI dependency providers for the agent-workspace facets.

Split out of ``agent_dependencies`` (specs agent-registry and skill-manager,
workspace amendment) for the file-size budget. Same ``set_*`` / ``get_*``
singleton shape, typed concretely.
"""

from __future__ import annotations

from coffer.application.agent.agent_sessions_listing import AgentSessionsListing
from coffer.application.agent.hooks_service import AgentHooksService
from coffer.application.agent.mcp_entry_service import AgentMcpEntryService
from coffer.application.agent.native_memory_service import AgentNativeMemoryService
from coffer.application.agent.native_session_service import NativeSessionService
from coffer.application.agent.plugin_service import AgentPluginService

_agent_mcp_entry_service: AgentMcpEntryService | None = None


def set_agent_mcp_entry_service(svc: AgentMcpEntryService) -> None:
    """Called by the composition root once on startup."""
    global _agent_mcp_entry_service
    _agent_mcp_entry_service = svc


def get_agent_mcp_entry_service() -> AgentMcpEntryService:
    """FastAPI Depends() target."""
    if _agent_mcp_entry_service is None:
        raise RuntimeError("agent MCP-entry service not initialised")
    return _agent_mcp_entry_service


_agent_plugin_service: AgentPluginService | None = None


def set_agent_plugin_service(svc: AgentPluginService) -> None:
    """Called by the composition root once on startup."""
    global _agent_plugin_service
    _agent_plugin_service = svc


def get_agent_plugin_service() -> AgentPluginService:
    """FastAPI Depends() target."""
    if _agent_plugin_service is None:
        raise RuntimeError("agent plugin service not initialised")
    return _agent_plugin_service


_agent_native_memory_service: AgentNativeMemoryService | None = None


def set_agent_native_memory_service(svc: AgentNativeMemoryService) -> None:
    """Called by the composition root once on startup."""
    global _agent_native_memory_service
    _agent_native_memory_service = svc


def get_agent_native_memory_service() -> AgentNativeMemoryService:
    """FastAPI Depends() target."""
    if _agent_native_memory_service is None:
        raise RuntimeError("agent native-memory service not initialised")
    return _agent_native_memory_service


_native_session_service: NativeSessionService | None = None


def set_native_session_service(svc: NativeSessionService) -> None:
    """Called by the composition root once on startup."""
    global _native_session_service
    _native_session_service = svc


def get_native_session_service() -> NativeSessionService:
    """FastAPI Depends() target."""
    if _native_session_service is None:
        raise RuntimeError("native session service not initialised")
    return _native_session_service


_agent_sessions_listing: AgentSessionsListing | None = None


def set_agent_sessions_listing(svc: AgentSessionsListing) -> None:
    """Called by the composition root once on startup."""
    global _agent_sessions_listing
    _agent_sessions_listing = svc


def get_agent_sessions_listing() -> AgentSessionsListing:
    """FastAPI Depends() target."""
    if _agent_sessions_listing is None:
        raise RuntimeError("agent sessions listing not initialised")
    return _agent_sessions_listing


_agent_hooks_service: AgentHooksService | None = None


def set_agent_hooks_service(svc: AgentHooksService) -> None:
    """Called by the composition root once on startup."""
    global _agent_hooks_service
    _agent_hooks_service = svc


def get_agent_hooks_service() -> AgentHooksService:
    """FastAPI Depends() target."""
    if _agent_hooks_service is None:
        raise RuntimeError("agent hooks service not initialised")
    return _agent_hooks_service
