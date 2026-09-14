"""Per-agent scope filtering for the MCP gateway session (ADR per-agent-resource-scope).

Extracted from `gateway.py` to keep that file under the project's 400-LOC
ceiling. Filters the enabled mcp_server resource list down to the servers
this session's agent identity may see, pushing the enabled=true filter to
SQL so we don't materialise rows we'll throw away (CODE-021).
"""

from __future__ import annotations

from coffer.application.resource_service import ResourceService
from coffer.application.scope_evaluator import ScopeEvaluator


async def enabled_mcp_servers(
    resources: ResourceService,
    session_agent: str | None,
    scope: ScopeEvaluator,
) -> list[str]:
    """Return the enabled mcp_server resource names visible to this session.

    A server with no scope is visible to everyone; a scoped one only to the
    agents it names, on the machines it names — ``scope`` carries this
    machine's id, so no caller here has to know that axis exists. A session
    that reported no identity (``session_agent is None`` — a hand-configured
    shim without ``--agent``) sees only servers with no agent axis, i.e.
    strictly less, never more.
    """
    resource_list = await resources.list(kind="mcp_server", enabled=True)
    return [r.name for r in resource_list if scope.is_active(r.scope, session_agent)]
