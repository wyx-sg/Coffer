"""Per-agent MCP server scoping helpers (ADR-026).

Extracted from gateway.py to keep the session class under its file-size
budget. The session simply delegates to these module-level helpers; the
scoping policy (enabled-server filtering + call-time authorization) lives
here.
"""

from __future__ import annotations

from coffer.application.mcp.ports import AgentMcpScopePort
from coffer.application.resource_service import ResourceService
from coffer.domain.scope_errors import AgentMcpServerNotInScope


async def allowed_server_names(
    scope: AgentMcpScopePort | None, agent_name: str | None
) -> set[str] | None:
    """The agent's allowlist (server names), or ``None`` when unscoped."""
    if scope is None or agent_name is None:
        return None
    return await scope.allowed_server_names(agent_name)


async def effective_mcp_servers(
    resources: ResourceService,
    scope: AgentMcpScopePort | None,
    agent_name: str | None,
) -> list[str]:
    # Enabled servers, narrowed to the agent's scope (ADR-026). Push the
    # enabled=true filter to SQL so we don't materialise rows we'll throw
    # away (CODE-021). An unscoped session (no agent identity / auto mode)
    # sees every enabled server — the prior whole-gateway-per-agent default.
    servers = await resources.list(kind="mcp_server", enabled=True)
    allowed = await allowed_server_names(scope, agent_name)
    if allowed is None:
        return [r.name for r in servers]
    return [r.name for r in servers if r.name in allowed]


async def authorize_server(
    scope: AgentMcpScopePort | None, agent_name: str | None, server_name: str
) -> None:
    # Reject a direct call/read/get to a server outside the agent's scope.
    # List-time hiding alone is insufficient — a model can name a
    # ``server__tool`` directly — so the call path is gated too (FR-022).
    allowed = await allowed_server_names(scope, agent_name)
    if allowed is not None and server_name not in allowed:
        raise AgentMcpServerNotInScope(server_name)
