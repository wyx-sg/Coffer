"""FastAPI dependency providers for the MCP kind.

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.dependencies``,
typed concretely: this module belongs to the MCP kind, so it may name the
kind's own services and repos, and the kind-agnostic hub never has to.

It also holds ``require_mcp_server``, the one place the ``{uid}`` in an
MCP route's path becomes the row behind it — shared here rather than repeated
in each of the three route modules that need it.
"""

from __future__ import annotations

from collections.abc import Callable

from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
    MCPServerHealthRepo,
)

#: The kind every route under ``/resources/mcp_server/{uid}`` promises to be
#: addressing. Spelled here rather than imported because the MCP application
#: package has no constant for it and inventing a cross-package import for one
#: string literal would cost more than it saves.
_KIND_MCP_SERVER = "mcp_server"

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


async def require_mcp_server(uid: str, resources: ResourceService) -> Resource:
    """The ``mcp_server`` :class:`Resource` ``uid`` names, or 404.

    Hands the **row** back rather than only asserting it exists, because every
    caller needs something off it that the path does not carry. Capability
    discovery is keyed on the server's NAME — the namespace a tool is published
    under on the MCP wire is ``<server>__<tool>``, and that namespace is the
    label — so a route addressed by identity still has to learn the label
    before it can query anything. Resolving once here is what keeps that from
    being a lookup each handler repeats, and what pins the label a handler uses
    to the one the row carried at this instant.

    A uid belonging to some *other* kind is refused with the same 404
    (``RESOURCE_NOT_FOUND``) as a uid nothing answers to. That check is not
    ceremony: while the name was the identity, ``(kind, name)`` lookups could
    not reach across kinds at all, and this restores that guarantee. Without
    it, a skill's uid would resolve here and the handler would go on to
    validate a skill's config as an ``MCPServerConfig``, or write a health row
    against a resource that is not a server.
    """
    resource = await resources.get(uid)
    if resource.kind != _KIND_MCP_SERVER:
        raise ResourceNotFound(uid)
    return resource
