"""FastAPI dependency providers — composition root sets these at startup."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from fastapi import Header, HTTPException, status

from coffer.application.audit_service import AuditService
from coffer.application.embedding_config_service import EmbeddingConfigService
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService

# Agent-chat (spec 008) providers re-exported so the get_chat_service paths work.
from coffer.surfaces.http.chat.dependencies import (
    get_agent_registry as get_agent_registry,
)
from coffer.surfaces.http.chat.dependencies import (
    get_chat_service as get_chat_service,
)
from coffer.surfaces.http.chat.dependencies import (
    get_model_service as get_model_service,
)
from coffer.surfaces.http.chat.dependencies import (
    get_turn_orchestrator as get_turn_orchestrator,
)
from coffer.surfaces.http.chat.dependencies import (
    set_agent_registry as set_agent_registry,
)
from coffer.surfaces.http.chat.dependencies import (
    set_chat_service as set_chat_service,
)
from coffer.surfaces.http.chat.dependencies import (
    set_model_service as set_model_service,
)
from coffer.surfaces.http.chat.dependencies import (
    set_turn_orchestrator as set_turn_orchestrator,
)

# X-Coffer-Actor: any short bounded identifier (canonical "cli"/"api"/"ui"/
# "system"; prefixed ones like "e2e-mcp" allowed). Absence defaults to "api".
_ACTOR_PATTERN: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def get_actor(x_coffer_actor: str | None = Header(default=None)) -> str:
    """Actor name for audit entries from X-Coffer-Actor (``"api"`` when absent).

    Rejects values that are not short lowercase identifiers (1-32 chars,
    ``[a-z][a-z0-9_-]*``) with 400 so audit entries stay safe and bounded."""
    if x_coffer_actor is None or x_coffer_actor == "":
        return "api"
    if not _ACTOR_PATTERN.match(x_coffer_actor):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid actor: {x_coffer_actor!r}",
        )
    return x_coffer_actor


_resource_service: ResourceService | None = None


def set_resource_service(svc: ResourceService) -> None:
    """Called by the composition root once on startup."""
    global _resource_service
    _resource_service = svc


def get_resource_service() -> ResourceService:
    """FastAPI Depends() target."""
    if _resource_service is None:
        raise RuntimeError("resource service not initialised")
    return _resource_service


_audit_service: AuditService | None = None


def set_audit_service(svc: AuditService) -> None:
    """Called by the composition root once on startup."""
    global _audit_service
    _audit_service = svc


def get_audit_service() -> AuditService:
    """FastAPI Depends() target."""
    if _audit_service is None:
        raise RuntimeError("audit service not initialised")
    return _audit_service


_retention_service: RetentionService | None = None


def set_retention_service(svc: RetentionService) -> None:
    """Called by the composition root once on startup."""
    global _retention_service
    _retention_service = svc


def get_retention_service() -> RetentionService:
    """FastAPI Depends() target."""
    if _retention_service is None:
        raise RuntimeError("retention service not initialised")
    return _retention_service


_embedding_config_service: EmbeddingConfigService | None = None


def set_embedding_config_service(svc: EmbeddingConfigService) -> None:
    """Called by the composition root once on startup."""
    global _embedding_config_service
    _embedding_config_service = svc


def get_embedding_config_service() -> EmbeddingConfigService:
    """FastAPI Depends() target."""
    if _embedding_config_service is None:
        raise RuntimeError("embedding config service not initialised")
    return _embedding_config_service


# Factory (session_id: str) -> <MCPGatewaySession>; typed Callable[[str], Any] to
# keep it out of kind-agnostic surfaces (Contract 6; enforced at mcp.protocol_routes).
_mcp_session_factory: Callable[[str], Any] | None = None


def set_mcp_session_factory(factory: Callable[[str], Any]) -> None:
    """Called by the composition root once on startup."""
    global _mcp_session_factory
    _mcp_session_factory = factory


def get_mcp_session_factory() -> Callable[[str], Any]:
    """FastAPI Depends() target."""
    if _mcp_session_factory is None:
        raise RuntimeError("MCP session factory not initialised")
    return _mcp_session_factory


# --- MCP kind-specific dependency providers (typed Any per Contract 6;
# concrete types enforced at the mcp.* route call sites) ---
_capability_discovery: Any | None = None
_supervisor: Any | None = None
_preferences_repo: Any | None = None
_invocation_repo: Any | None = None
_health_repo: Any | None = None


def set_capability_discovery(discovery: Any) -> None:
    """Called by the composition root once on startup."""
    global _capability_discovery
    _capability_discovery = discovery


def get_capability_discovery() -> Any:
    """FastAPI Depends() target — actual type is CapabilityDiscovery."""
    if _capability_discovery is None:
        raise RuntimeError("capability discovery not initialised")
    return _capability_discovery


def set_supervisor(supervisor: Any) -> None:
    """Called by the composition root once on startup."""
    global _supervisor
    _supervisor = supervisor


def get_supervisor() -> Any:
    """FastAPI Depends() target — actual type is SubprocessSupervisor."""
    if _supervisor is None:
        raise RuntimeError("supervisor not initialised")
    return _supervisor


def set_preferences_repo(repo: Any) -> None:
    """Called by the composition root once on startup."""
    global _preferences_repo
    _preferences_repo = repo


def get_preferences_repo() -> Any:
    """FastAPI Depends() target — actual type is MCPCapabilityPreferenceRepo."""
    if _preferences_repo is None:
        raise RuntimeError("preferences repo not initialised")
    return _preferences_repo


def set_invocation_repo(repo: Any) -> None:
    """Called by the composition root once on startup."""
    global _invocation_repo
    _invocation_repo = repo


def get_invocation_repo_optional() -> Any | None:
    """Buffered invocation repo (None if no MCP kind wired); lets the app
    lifespan start()/stop() the writer (CODE-DI)."""
    return _invocation_repo


def get_invocation_repo() -> Any:
    """FastAPI Depends() target — actual type is MCPInvocationRepo."""
    repo = get_invocation_repo_optional()
    if repo is None:
        raise RuntimeError("invocation repo not initialised")
    return repo


def set_health_repo(repo: Any) -> None:
    """Called by the composition root once on startup."""
    global _health_repo
    _health_repo = repo


def get_health_repo() -> Any:
    """FastAPI Depends() target — actual type is MCPServerHealthRepo."""
    if _health_repo is None:
        raise RuntimeError("health repo not initialised")
    return _health_repo


# Credential-store DI singletons re-exported from credential_composition (split
# for the file-size limit) so their import paths keep working.
from coffer.surfaces.http.credential_composition import (  # noqa: E402, I001
    get_credential_store as get_credential_store,
    get_master_key_manager as get_master_key_manager,
    set_credential_store as set_credential_store,
    set_master_key_manager as set_master_key_manager,
)

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


# --- Skill kind (spec 005-skill-manager) ---

_skill_service: Any | None = None


def set_skill_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _skill_service
    _skill_service = svc


def get_skill_service() -> Any:
    """FastAPI Depends() target — actual type is SkillService."""
    if _skill_service is None:
        raise RuntimeError("skill service not initialised")
    return _skill_service


# --- knowledge_base kind (spec 006-knowledge-base) ---

_kb_service: Any | None = None


def set_kb_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _kb_service
    _kb_service = svc


def get_kb_service() -> Any:
    """FastAPI Depends() target — actual type is KnowledgeBaseService."""
    if _kb_service is None:
        raise RuntimeError("knowledge base service not initialised")
    return _kb_service


# --- memory kind dependency providers (spec 007) ---
_memory_service: Any | None = None


def set_memory_service(svc: Any) -> None:
    global _memory_service
    _memory_service = svc


def get_memory_service() -> Any:
    if _memory_service is None:
        raise RuntimeError("memory service not initialised")
    return _memory_service


# More providers split out for the file-size budget: memory.dependencies,
# distill.state, chat.dependencies (re-exported at top).
