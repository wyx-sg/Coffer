"""FastAPI dependency providers for the agent kind (spec agent-registry).

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.dependencies``,
typed concretely. The agent-workspace facets (MCP entries, plugins, native
memory, transcripts) live in ``workspace_dependencies`` for the file-size
budget.
"""

from __future__ import annotations

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.config_file_service import AgentConfigFileService
from coffer.application.agent.mcp_service import AgentMcpService
from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.application.agent.service import AgentService
from coffer.application.fs.browse_service import FsBrowseService

_agent_service: AgentService | None = None


def set_agent_service(svc: AgentService) -> None:
    """Called by the composition root once on startup."""
    global _agent_service
    _agent_service = svc


def get_agent_service() -> AgentService:
    """FastAPI Depends() target."""
    if _agent_service is None:
        raise RuntimeError("agent service not initialised")
    return _agent_service


_auto_detect_service: AutoDetectService | None = None


def set_auto_detect_service(svc: AutoDetectService) -> None:
    """Called by the composition root once on startup."""
    global _auto_detect_service
    _auto_detect_service = svc


def get_auto_detect_service() -> AutoDetectService:
    """FastAPI Depends() target."""
    if _auto_detect_service is None:
        raise RuntimeError("auto-detect service not initialised")
    return _auto_detect_service


_agent_config_file_service: AgentConfigFileService | None = None


def set_agent_config_file_service(svc: AgentConfigFileService) -> None:
    """Called by the composition root once on startup."""
    global _agent_config_file_service
    _agent_config_file_service = svc


def get_agent_config_file_service() -> AgentConfigFileService:
    """FastAPI Depends() target."""
    if _agent_config_file_service is None:
        raise RuntimeError("agent config-file service not initialised")
    return _agent_config_file_service


_agent_mcp_service: AgentMcpService | None = None


def set_agent_mcp_service(svc: AgentMcpService) -> None:
    """Called by the composition root once on startup."""
    global _agent_mcp_service
    _agent_mcp_service = svc


def get_agent_mcp_service() -> AgentMcpService:
    """FastAPI Depends() target."""
    if _agent_mcp_service is None:
        raise RuntimeError("agent MCP service not initialised")
    return _agent_mcp_service


_agent_model_catalogue: AgentModelCatalogueService | None = None


def set_agent_model_catalogue(svc: AgentModelCatalogueService) -> None:
    """Called by the composition root once on startup."""
    global _agent_model_catalogue
    _agent_model_catalogue = svc


def get_agent_model_catalogue() -> AgentModelCatalogueService:
    """FastAPI Depends() target."""
    if _agent_model_catalogue is None:
        raise RuntimeError("agent model catalogue not initialised")
    return _agent_model_catalogue


def get_fs_browse_service() -> FsBrowseService:
    """FastAPI Depends() target. Stateless, so it is built per request."""
    return FsBrowseService()
