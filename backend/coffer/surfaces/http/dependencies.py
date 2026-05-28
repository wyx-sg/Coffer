"""FastAPI dependency providers — composition root sets these at startup."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from fastapi import Header, HTTPException, status

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

# X-Coffer-Actor accepts any short identifier. Canonical values: "cli", "api",
# "ui", "system". Tests use prefixed identifiers like "e2e-mcp"; downstream
# integrations may add their own. Length-and-charset bounded to keep audit
# safe; absence defaults to "api".
_ACTOR_PATTERN: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def get_actor(x_coffer_actor: str | None = Header(default=None)) -> str:
    """Resolve the actor name for audit log entries from X-Coffer-Actor header.

    Falls back to ``"api"`` when the header is absent. Rejects values that are
    not short lowercase identifiers (1-32 chars, ``[a-z][a-z0-9_-]*``) with 400
    so audit entries always carry a safe, bounded string.
    """
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


# Factory type: (session_id: str) -> <MCPGatewaySession>.
# Typed as Callable[[str], Any] to avoid importing MCPGatewaySession here and
# creating a transitive kind-specific import chain from kind-agnostic surfaces
# (Contract 6).  The concrete MCPGatewaySession type is enforced at the call
# site in coffer.surfaces.http.mcp.protocol_routes, which IS in the mcp kind.
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


# --- MCP kind-specific dependency providers ---
# These are typed as Any to avoid importing kind-specific modules from the
# kind-agnostic core (Contract 6). The concrete types are enforced at the
# call site in coffer.surfaces.http.mcp.* route modules.

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


def get_invocation_repo() -> Any:
    """FastAPI Depends() target — actual type is MCPInvocationRepo."""
    if _invocation_repo is None:
        raise RuntimeError("invocation repo not initialised")
    return _invocation_repo


def set_health_repo(repo: Any) -> None:
    """Called by the composition root once on startup."""
    global _health_repo
    _health_repo = repo


def get_health_repo() -> Any:
    """FastAPI Depends() target — actual type is MCPServerHealthRepo."""
    if _health_repo is None:
        raise RuntimeError("health repo not initialised")
    return _health_repo


def get_keyring() -> KeyringAdapter:
    """FastAPI Depends() target — the keychain bridge is stateless."""
    return KeyringAdapter()
