"""ADR-045 machine x agent scope-filtering helpers for the MCP gateway session.

Extracted from `gateway.py` to keep that file under the project's 400-LOC
ceiling. Two concerns live here:

1. Resolving + caching the session's local machine id (Task 8): the
   provider is a coroutine that hits the sync-identity store, so it is
   called once per session and cached — mirroring ChannelRuntime
   (channel/runtime.py:181-186).
2. Filtering the enabled mcp_server resource list down to the servers this
   (machine, agent) pair may see (Tasks 8/9), pushing the enabled=true
   filter to SQL so we don't materialise rows we'll throw away (CODE-021).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from coffer.application.resource_service import ResourceService
from coffer.domain.scope import agent_in_scope, machine_in_scope

MachineIdProvider = Callable[[], Awaitable[str | None]]


async def resolve_local_machine_id(
    provider: MachineIdProvider | None,
    cached: str | None,
) -> str | None:
    """Resolve this session's local machine id, honoring an already-cached value.

    ``provider`` is None when no sync identity is wired (legacy behavior — no
    filtering). ``cached`` is the session's previously-resolved value, if any;
    passing it back through avoids a second call to ``provider`` per session.
    """
    if provider is None:
        return None
    if cached is not None:
        return cached
    return await provider()


async def enabled_mcp_servers(
    resources: ResourceService,
    local_machine_id: str | None,
    session_agent: str | None,
) -> list[str]:
    """Return the enabled mcp_server resource names visible to this session.

    No filtering is applied when ``local_machine_id`` is None (no sync
    identity provider wired). Otherwise a server is included only when both
    the machine and agent axes admit this session (ADR-045).
    """
    resource_list = await resources.list(kind="mcp_server", enabled=True)
    enabled_names: list[str] = []
    for r in resource_list:
        if local_machine_id is not None and not machine_in_scope(r.scope, local_machine_id):
            continue
        if local_machine_id is not None and not agent_in_scope(
            r.scope, local_machine_id, session_agent
        ):
            continue
        enabled_names.append(r.name)
    return enabled_names
