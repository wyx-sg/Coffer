"""Per-agent scope filtering for the MCP gateway session (ADR per-agent-resource-scope).

Extracted from `gateway.py` to keep that file under the project's 400-LOC
ceiling. Filters the enabled mcp_server resource list down to the servers
this session's agent identity may see, pushing the enabled=true filter to
SQL so we don't materialise rows we'll throw away.
"""

from __future__ import annotations

from coffer.application.resource_service import ResourceService
from coffer.domain.scope import is_active


async def enabled_mcp_servers(
    resources: ResourceService,
    session_agent_uid: str | None,
) -> list[str]:
    """Return the enabled mcp_server resource names visible to this session.

    A server with no scope is visible to everyone; a scoped one only to the
    agents whose **uid** it names — a scope is a reference to another resource,
    so it holds the identity, not the label (ADR
    resource-identity-is-an-immutable-uid). A session that reported no identity
    (``session_agent_uid is None`` — a hand-configured shim, or one installed by
    a Coffer old enough to have written ``--agent <name>``) sees only unscoped
    servers, i.e. strictly less, never more.

    Names come back rather than uids because the caller's next move is to build
    the namespaced wire entries (``<server>__<tool>``) the downstream client
    addresses, and that namespace is the label.
    """
    resource_list = await resources.list(kind="mcp_server", enabled=True)
    return [r.name for r in resource_list if is_active(r.scope, session_agent_uid)]
