"""Agent-kind FastAPI dependency providers (spec 004-agent-registry).

Split out of :mod:`coffer.surfaces.http.dependencies` for the file-size budget.
Re-exported there so existing ``from ...dependencies import get_agent_service``
import paths keep working. Typed ``Any`` per Contract 6; concrete types are
enforced at the agent.* route call sites.
"""

from __future__ import annotations

from typing import Any

# --- Agent kind-specific dependency providers (spec 004-agent-registry) ---
_agent_service: Any | None = None
_auto_detect_service: Any | None = None


def set_agent_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _agent_service
    _agent_service = svc


def get_agent_service() -> Any:
    """FastAPI Depends() target — actual type is AgentService."""
    if _agent_service is None:
        raise RuntimeError("agent service not initialised")
    return _agent_service


_provider_service: Any | None = None


def set_provider_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _provider_service
    _provider_service = svc


def get_provider_service() -> Any:
    """FastAPI Depends() target — actual type is ProviderService (spec 011)."""
    if _provider_service is None:
        raise RuntimeError("provider service not initialised")
    return _provider_service


def set_auto_detect_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _auto_detect_service
    _auto_detect_service = svc


def get_auto_detect_service() -> Any:
    """FastAPI Depends() target — actual type is AutoDetectService."""
    if _auto_detect_service is None:
        raise RuntimeError("auto-detect service not initialised")
    return _auto_detect_service


_agent_config_file_service: Any | None = None
_agent_mcp_service: Any | None = None
_agent_native_memory_service: Any | None = None


def set_agent_config_file_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _agent_config_file_service
    _agent_config_file_service = svc


def get_agent_config_file_service() -> Any:
    """FastAPI Depends() target — actual type is AgentConfigFileService."""
    if _agent_config_file_service is None:
        raise RuntimeError("agent config-file service not initialised")
    return _agent_config_file_service


def set_agent_mcp_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _agent_mcp_service
    _agent_mcp_service = svc


def get_agent_mcp_service() -> Any:
    """FastAPI Depends() target — actual type is AgentMcpService."""
    if _agent_mcp_service is None:
        raise RuntimeError("agent MCP service not initialised")
    return _agent_mcp_service


_agent_hook_service: Any | None = None


def set_agent_hook_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _agent_hook_service
    _agent_hook_service = svc


def get_agent_hook_service() -> Any:
    """FastAPI Depends() target — actual type is AgentHookService."""
    if _agent_hook_service is None:
        raise RuntimeError("agent hook service not initialised")
    return _agent_hook_service


def set_agent_native_memory_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _agent_native_memory_service
    _agent_native_memory_service = svc


def get_agent_native_memory_service() -> Any:
    """FastAPI Depends() target — actual type is AgentNativeMemoryService."""
    if _agent_native_memory_service is None:
        raise RuntimeError("agent native-memory service not initialised")
    return _agent_native_memory_service


_agent_memory_import_service: Any | None = None


def set_agent_memory_import_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _agent_memory_import_service
    _agent_memory_import_service = svc


def get_agent_memory_import_service() -> Any:
    """FastAPI Depends() target — actual type is AgentMemoryImportService."""
    if _agent_memory_import_service is None:
        raise RuntimeError("agent memory-import service not initialised")
    return _agent_memory_import_service


def get_fs_browse_service() -> Any:
    """FastAPI Depends() target (FsBrowseService). Stateless → built per-request."""
    from coffer.application.fs.browse_service import FsBrowseService

    return FsBrowseService()
