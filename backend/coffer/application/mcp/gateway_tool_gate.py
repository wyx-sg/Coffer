"""The per-tool gate for custom tools (spec mcp-gateway "Switch off or narrow
one custom tool"; design add-http-custom-tools §6).

A custom-tool group's tools each carry an on/off switch in the group's config
and may carry a reach override (machine-local, in ``mcp_tool_reach``). The
gateway hides a switched-off tool, and one whose override does not admit the
session's agent, from ``tools/list`` and ``coffer__search_tools``, and refuses
a call on it exactly as it refuses a disabled capability. An override narrows
the group's own reach: the group-level gate (``gateway_scope``) has already
hidden every tool of a group the agent is not reached by.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence

from pydantic import ValidationError

from coffer.application.mcp.custom_tool_ports import ToolReachRepoPort
from coffer.domain.mcp.http_api import HttpApiTransport
from coffer.domain.mcp.namespace import prefix_tool
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope, is_active


def http_api_transport(resource: Resource) -> HttpApiTransport | None:
    """The group's transport when ``resource`` is a custom-tool group."""
    transport = resource.config.get("transport") if isinstance(resource.config, dict) else None
    if not isinstance(transport, dict) or transport.get("type") != "http_api":
        return None
    with contextlib.suppress(ValidationError):
        parsed = MCPServerConfig.model_validate(resource.config).transport
        if isinstance(parsed, HttpApiTransport):
            return parsed
    return None


def _admits(override: list[str] | None, agent_uid: str | None) -> bool:
    return override is None or is_active(Scope(agents=override), agent_uid)


async def hidden_tool_names(
    resources: Sequence[Resource],
    agent_uid: str | None,
    reach: ToolReachRepoPort | None,
) -> frozenset[str]:
    """Namespaced names of the custom tools this agent must not see."""
    groups = [(r, t) for r in resources if (t := http_api_transport(r)) is not None]
    if not groups:
        return frozenset()
    overrides = await reach.overrides_for([r.uid for r, _ in groups]) if reach else {}
    hidden: set[str] = set()
    for resource, transport in groups:
        per_tool = overrides.get(resource.uid, {})
        for tool in transport.tools:
            if not tool.enabled or not _admits(per_tool.get(tool.name), agent_uid):
                hidden.add(prefix_tool(resource.name, tool.name))
    return frozenset(hidden)


async def custom_tool_denial(
    resource: Resource,
    tool_name: str,
    agent_uid: str | None,
    reach: ToolReachRepoPort | None,
) -> str | None:
    """Why a call on ``tool_name`` is refused for this agent, or None."""
    transport = http_api_transport(resource)
    if transport is None:
        return None
    tool = transport.tool(tool_name)
    if tool is None:
        return None  # the adapter answers an unknown tool itself
    if not tool.enabled:
        return f"tool:{tool_name!r} is switched off in {resource.name!r}"
    if reach is not None:
        overrides = await reach.overrides_for([resource.uid])
        if not _admits(overrides.get(resource.uid, {}).get(tool_name), agent_uid):
            return f"tool:{tool_name!r} is not in reach here"
    return None


__all__ = ["custom_tool_denial", "hidden_tool_names", "http_api_transport"]
