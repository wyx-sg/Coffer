"""The per-tool gate for custom tools (spec mcp-gateway "Switch off one custom
tool"; design add-http-custom-tools §6).

A custom-tool group's tools each carry an on/off switch in the group's config.
The gateway hides a switched-off tool from ``tools/list`` and
``coffer__search_tools``, and refuses a call on it exactly as it refuses a
disabled capability. Who can see a tool is the group's reach alone: the
group-level gate (``gateway_scope``) hides every tool of a group the agent is
not reached by.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence

from pydantic import ValidationError

from coffer.domain.mcp.http_api import HttpApiTransport
from coffer.domain.mcp.namespace import prefix_tool
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Resource


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


def hidden_tool_names(resources: Sequence[Resource]) -> frozenset[str]:
    """Namespaced names of the switched-off custom tools."""
    hidden: set[str] = set()
    for resource in resources:
        transport = http_api_transport(resource)
        if transport is None:
            continue
        for tool in transport.tools:
            if not tool.enabled:
                hidden.add(prefix_tool(resource.name, tool.name))
    return frozenset(hidden)


def custom_tool_denial(resource: Resource, tool_name: str) -> str | None:
    """Why a call on ``tool_name`` is refused, or None."""
    transport = http_api_transport(resource)
    if transport is None:
        return None
    tool = transport.tool(tool_name)
    if tool is None:
        return None  # the adapter answers an unknown tool itself
    if not tool.enabled:
        return f"tool:{tool_name!r} is switched off in {resource.name!r}"
    return None


__all__ = ["custom_tool_denial", "hidden_tool_names", "http_api_transport"]
