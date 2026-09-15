"""FastAPI dependency providers for the agent-workspace facets.

Split out of ``agent_dependencies`` (specs agent-registry and skill-manager,
workspace amendment) for the file-size budget. Same ``set_*`` / ``get_*``
singleton shape, typed concretely.
"""

from __future__ import annotations

from coffer.application.agent.mcp_entry_service import AgentMcpEntryService
from coffer.application.agent.native_memory_service import AgentNativeMemoryService
from coffer.application.agent.plugin_service import AgentPluginService
from coffer.application.agent.transcript_service import AgentTranscriptService

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


_agent_transcript_service: AgentTranscriptService | None = None


def set_agent_transcript_service(svc: AgentTranscriptService) -> None:
    """Called by the composition root once on startup."""
    global _agent_transcript_service
    _agent_transcript_service = svc


def get_agent_transcript_service() -> AgentTranscriptService:
    """FastAPI Depends() target."""
    if _agent_transcript_service is None:
        raise RuntimeError("agent transcript service not initialised")
    return _agent_transcript_service
