"""FastAPI dependency providers for the MCP kind.

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.dependencies``,
typed concretely: this module belongs to the MCP kind, so it may name the
kind's own services and repos, and the kind-agnostic hub never has to.
"""

from __future__ import annotations

from collections.abc import Callable

from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
    MCPServerHealthRepo,
)

#: Builds one ``MCPGatewaySession`` per ``/mcp`` session id.
McpSessionFactory = Callable[[str], MCPGatewaySession]

_mcp_session_factory: McpSessionFactory | None = None


def set_mcp_session_factory(factory: McpSessionFactory) -> None:
    """Called by the composition root once on startup."""
    global _mcp_session_factory
    _mcp_session_factory = factory


def get_mcp_session_factory() -> McpSessionFactory:
    """FastAPI Depends() target."""
    if _mcp_session_factory is None:
        raise RuntimeError("MCP session factory not initialised")
    return _mcp_session_factory


_capability_discovery: CapabilityDiscovery | None = None


def set_capability_discovery(discovery: CapabilityDiscovery) -> None:
    """Called by the composition root once on startup."""
    global _capability_discovery
    _capability_discovery = discovery


def get_capability_discovery() -> CapabilityDiscovery:
    """FastAPI Depends() target."""
    if _capability_discovery is None:
        raise RuntimeError("capability discovery not initialised")
    return _capability_discovery


_preferences_repo: MCPCapabilityPreferenceRepo | None = None


def set_preferences_repo(repo: MCPCapabilityPreferenceRepo) -> None:
    """Called by the composition root once on startup."""
    global _preferences_repo
    _preferences_repo = repo


def get_preferences_repo() -> MCPCapabilityPreferenceRepo:
    """FastAPI Depends() target."""
    if _preferences_repo is None:
        raise RuntimeError("preferences repo not initialised")
    return _preferences_repo


_invocation_repo: MCPInvocationRepo | None = None


def set_invocation_repo(repo: MCPInvocationRepo) -> None:
    """Called by the composition root once on startup."""
    global _invocation_repo
    _invocation_repo = repo


def get_invocation_repo_optional() -> MCPInvocationRepo | None:
    """The buffered invocation repo, or ``None`` when no MCP kind is wired."""
    return _invocation_repo


def get_invocation_repo() -> MCPInvocationRepo:
    """FastAPI Depends() target."""
    repo = get_invocation_repo_optional()
    if repo is None:
        raise RuntimeError("invocation repo not initialised")
    return repo


_health_repo: MCPServerHealthRepo | None = None


def set_health_repo(repo: MCPServerHealthRepo) -> None:
    """Called by the composition root once on startup."""
    global _health_repo
    _health_repo = repo


def get_health_repo_optional() -> MCPServerHealthRepo | None:
    """The health repo if initialised, else ``None`` — for ``/daemon/status``,
    which must answer during startup before the MCP kind is wired."""
    return _health_repo


def get_health_repo() -> MCPServerHealthRepo:
    """FastAPI Depends() target."""
    if _health_repo is None:
        raise RuntimeError("health repo not initialised")
    return _health_repo
