"""ADR-045 per-agent scope filtering for the MCP gateway session.

Extracted from `gateway.py` to keep that file under the project's 400-LOC
ceiling. Filters the enabled mcp_server resource list down to the servers
this session's agent identity may see, pushing the enabled=true filter to
SQL so we don't materialise rows we'll throw away (CODE-021).
"""

from __future__ import annotations

from coffer.application.resource_service import ResourceService
from coffer.domain.scope import agent_in_scope


async def enabled_mcp_servers(
    resources: ResourceService,
    session_agent: str | None,
) -> list[str]:
    """Return the enabled mcp_server resource names visible to this session.

    A server with no scope is visible to everyone; a scoped one only to the
    agents it names. A session that reported no identity (``session_agent is
    None`` — a hand-configured shim without ``--agent``) sees only unscoped
    servers, i.e. strictly less, never more.
    """
    resource_list = await resources.list(kind="mcp_server", enabled=True)
    return [r.name for r in resource_list if agent_in_scope(r.scope, session_agent)]
