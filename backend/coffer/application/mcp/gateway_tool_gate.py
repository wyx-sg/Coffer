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
from coffer.domain.mcp.http_api_environment import ENVIRONMENT_ARG
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


def group_descriptions(resources: Sequence[Resource]) -> dict[str, str]:
    """``{group name: description}`` for the custom-tool groups that have one.

    Spec mcp-gateway "Describe a custom-tool group": ``coffer__search_tools``
    scores a group's tools against its description too.
    """
    return {
        r.name: r.description
        for r in resources
        if r.description and http_api_transport(r) is not None
    }


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


def custom_tool_environment(resource: Resource, arguments: object) -> str | None:
    """The environment a custom-tool call names, for its invocation row: the
    chosen one when the group has it, the sole enabled one when none is chosen,
    else ``None`` (the call is refused, and the log says no more than that)."""
    transport = http_api_transport(resource)
    if transport is None:
        return None
    chosen = arguments.get(ENVIRONMENT_ARG) if isinstance(arguments, dict) else None
    if isinstance(chosen, str) and chosen:
        return chosen if transport.environment(chosen) is not None else None
    enabled = [e.name for e in transport.environments if e.enabled]
    return enabled[0] if len(enabled) == 1 else None


__all__ = [
    "custom_tool_denial",
    "custom_tool_environment",
    "hidden_tool_names",
    "http_api_transport",
]
