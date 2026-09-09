"""FastAPI dependency providers — composition root sets these at startup."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Header, HTTPException, status

from coffer.application.audit_service import AuditService
from coffer.application.embedding_config_service import EmbeddingConfigService
from coffer.application.internal_engine_config_service import InternalEngineConfigService
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
    get_turn_orchestrator as get_turn_orchestrator,
)
from coffer.surfaces.http.chat.dependencies import (
    set_agent_registry as set_agent_registry,
)
from coffer.surfaces.http.chat.dependencies import (
    set_chat_service as set_chat_service,
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


_internal_engine_config_service: InternalEngineConfigService | None = None


def set_internal_engine_config_service(svc: InternalEngineConfigService) -> None:
    """Called by the composition root once on startup."""
    global _internal_engine_config_service
    _internal_engine_config_service = svc


def get_internal_engine_config_service() -> InternalEngineConfigService:
    """FastAPI Depends() target."""
    if _internal_engine_config_service is None:
        raise RuntimeError("internal engine config service not initialised")
    return _internal_engine_config_service


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


# ADR-045 machine axis (Task 8): this daemon's local machine id, so REST
# routes that build an upstream connection directly (bypassing the process
# supervisor — e.g. the mcp_server "test" route) can still gate on scope.
# Unlike the providers above, an unset provider is NOT an error: it means
# "no MachineIdentityService wired", the same legacy no-filtering state the
# supervisor/gateway treat a None ``machine_id`` callable as, so this getter
# never raises and instead falls back to a callable that always resolves to
# None.
_local_machine_id_provider: Callable[[], Awaitable[str | None]] | None = None


async def _no_local_machine_id() -> str | None:
    return None


def set_local_machine_id_provider(provider: Callable[[], Awaitable[str | None]]) -> None:
    """Called by the composition root once on startup."""
    global _local_machine_id_provider
    _local_machine_id_provider = provider


def get_local_machine_id_provider() -> Callable[[], Awaitable[str | None]]:
    """FastAPI Depends() target — a zero-arg async callable resolving this
    daemon's ADR-045 machine id (or None when no provider is wired)."""
    return _local_machine_id_provider or _no_local_machine_id


# Credential-store DI singletons re-exported from credential_composition (split
# for the file-size limit) so their import paths keep working.
from coffer.surfaces.http.credential_composition import (  # noqa: E402, I001
    get_credential_store as get_credential_store,
    get_master_key_manager as get_master_key_manager,
    set_credential_store as set_credential_store,
    set_master_key_manager as set_master_key_manager,
)

# --- Agent kind-specific dependency providers (spec 004-agent-registry) ---
# Split into dependencies_agent for the file-size budget; re-exported here so the
# existing `from ...dependencies import get_agent_service` paths keep working.
from coffer.surfaces.http.dependencies_agent import (  # noqa: E402
    get_agent_config_file_service as get_agent_config_file_service,
    get_agent_hook_service as get_agent_hook_service,
    get_agent_mcp_service as get_agent_mcp_service,
    get_agent_memory_import_service as get_agent_memory_import_service,
    get_agent_native_memory_service as get_agent_native_memory_service,
    get_agent_service as get_agent_service,
    get_auto_detect_service as get_auto_detect_service,
    get_fs_browse_service as get_fs_browse_service,
    get_native_import_batch_service as get_native_import_batch_service,
    get_native_import_batch_service_optional as get_native_import_batch_service_optional,
    get_provider_service as get_provider_service,
    set_agent_config_file_service as set_agent_config_file_service,
    set_agent_hook_service as set_agent_hook_service,
    set_agent_mcp_service as set_agent_mcp_service,
    set_agent_memory_import_service as set_agent_memory_import_service,
    set_agent_native_memory_service as set_agent_native_memory_service,
    set_native_import_batch_service as set_native_import_batch_service,
    set_agent_service as set_agent_service,
    set_auto_detect_service as set_auto_detect_service,
    set_provider_service as set_provider_service,
)


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


# --- session-end distiller (Slice 6 FR-051) ---
_session_end_distiller: Any | None = None


def set_session_end_distiller(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _session_end_distiller
    _session_end_distiller = svc


def get_session_end_distiller() -> Any:
    """FastAPI Depends() target — actual type is SessionEndDistiller."""
    if _session_end_distiller is None:
        raise RuntimeError("session-end distiller not initialised")
    return _session_end_distiller


# More providers split out for the file-size budget: memory.dependencies (incl.
# the spec-007 journal-lane provider — imported there directly by the composition
# roots, NOT re-exported here so kind-agnostic core stays clean), distill.state,
# chat.dependencies (re-exported at top).
