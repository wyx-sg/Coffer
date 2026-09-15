"""Kind-agnostic FastAPI dependency providers.

Each ``set_*`` / ``get_*`` pair is a module-global singleton: the composition
root (``app.py``'s lifespan) calls the setter once at startup, routes name the
getter as a ``Depends()`` target, and a getter called before its setter raises
rather than hand a route a ``None`` it will dereference later. Tests override
the same setters.

Only the kind-agnostic core lives here (Contract 6). Every kind publishes its
own services from its own module, typed concretely, so nothing in this file
needs ``Any`` and nothing here can pull a kind into the core:

- ``surfaces.http.mcp.dependencies``       — the MCP kind
- ``surfaces.http.agent_dependencies``     — the agent kind (with
  ``workspace_dependencies`` for the agent-workspace facets)
- ``surfaces.http.skill_dependencies``     — the skill kind
- ``surfaces.http.knowledge.dependencies`` — the knowledge kind
- ``surfaces.http.memory.dependencies``    — the memory kind
- ``surfaces.http.chat.dependencies``      — the turn platform (chat)
- ``surfaces.http.provider_dependencies``  — the provider kind
- ``surfaces.http.credential_composition`` — the credential store + master key
"""

from __future__ import annotations

import re

from fastapi import Header, HTTPException, status

from coffer.application.audit_service import AuditService
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService

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


def get_resource_service_optional() -> ResourceService | None:
    """The resource service if initialised, else ``None`` — for ``/daemon/status``,
    which must answer during startup before the composition root has run."""
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
