"""Assemble a ``CapabilityListOut`` for the MCP management detail page.

Two sources feed the same response shape: the live discovery results
(``live_capability_list``) and — when the upstream can't be reached — the
persisted enable/disable preferences (``cached_capability_list``). Split out of
``capability_routes`` so the route module stays a thin request handler.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from coffer.application.mcp.discovery import (
    DiscoveredPrompt,
    DiscoveredResource,
    DiscoveredTool,
)
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.namespace import prefix_prompt, prefix_resource_uri, prefix_tool
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceRepo
from coffer.surfaces.http.schemas import (
    CapabilityListOut,
    MCPPromptView,
    MCPResourceView,
    MCPToolView,
    _MCPPromptArgument,
)


def live_capability_list(
    name: str,
    tools: Sequence[DiscoveredTool],
    resources: Sequence[DiscoveredResource],
    prompts: Sequence[DiscoveredPrompt],
) -> CapabilityListOut:
    """The freshly-discovered capability list (``from_cache=False``)."""
    return CapabilityListOut(
        server_name=name,
        tools=[
            MCPToolView(
                prefixed_name=t.prefixed_name,
                original_name=t.original_name,
                description=t.description,
                input_schema=t.input_schema,
                enabled=t.enabled,
            )
            for t in tools
        ],
        resources=[
            MCPResourceView(
                prefixed_uri=r.prefixed_uri,
                original_uri=r.original_uri,
                name=r.name,
                description=r.description,
                mime_type=r.mime_type,
                enabled=r.enabled,
            )
            for r in resources
        ],
        prompts=[
            MCPPromptView(
                prefixed_name=p.prefixed_name,
                original_name=p.original_name,
                description=p.description,
                arguments=[
                    _MCPPromptArgument(
                        name=a.get("name", ""),
                        description=a.get("description"),
                        required=bool(a.get("required", False)),
                    )
                    for a in p.arguments
                ],
                enabled=p.enabled,
            )
            for p in prompts
        ],
        fetched_at=datetime.now(tz=UTC),
        from_cache=False,
    )


async def cached_capability_list(
    name: str,
    prefs: MCPCapabilityPreferenceRepo,
    resource_service: ResourceService,
) -> CapabilityListOut | None:
    """Build the capability list from persisted enable/disable preferences.

    The fallback path when the live upstream can't be queried (a disabled
    server, an unreachable one). Per ADR-004 the DB never stores tool schemas —
    only each capability's key and its ``enabled`` flag — so the views carry
    name + enabled with empty descriptions/schemas: enough for the management
    list and its toggles. Returns ``None`` when the server was never discovered
    (no rows) or is unknown, so the caller surfaces the upstream error instead
    of a misleadingly empty page.
    """
    try:
        resource = await resource_service.get(ResourceRef("mcp_server", name))
    except Exception:
        return None
    rows = await prefs.list_for(resource.id)
    if not rows:
        return None
    return CapabilityListOut(
        server_name=name,
        tools=[
            MCPToolView(
                prefixed_name=prefix_tool(name, row.capability_key),
                original_name=row.capability_key,
                description=None,
                input_schema={},
                enabled=row.enabled,
            )
            for row in rows
            if row.capability_type == "tool"
        ],
        resources=[
            MCPResourceView(
                prefixed_uri=prefix_resource_uri(name, row.capability_key),
                original_uri=row.capability_key,
                name=None,
                description=None,
                mime_type=None,
                enabled=row.enabled,
            )
            for row in rows
            if row.capability_type == "resource"
        ],
        prompts=[
            MCPPromptView(
                prefixed_name=prefix_prompt(name, row.capability_key),
                original_name=row.capability_key,
                description=None,
                arguments=[],
                enabled=row.enabled,
            )
            for row in rows
            if row.capability_type == "prompt"
        ],
        fetched_at=datetime.now(tz=UTC),
        from_cache=True,
    )


__all__: list[Any] = ["cached_capability_list", "live_capability_list"]
