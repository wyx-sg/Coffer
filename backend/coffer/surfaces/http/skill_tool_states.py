"""The state of the MCP servers and custom-tool groups a skill names in
``requires: tools:`` (spec skill-manager "Declare the tools a skill requires").

The two kinds meet here, at the surface: both are ``mcp_server`` resources, a
custom-tool group by its ``http_api`` transport. Off is the resource's switch;
failing is the persisted health row its last connection test wrote, read from
the store the MCP routes publish (absent in a graph built without it)."""

from __future__ import annotations

from collections.abc import Mapping

from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.skill.tool_state import ToolKind, ToolState, ToolStatus
from coffer.surfaces.http.mcp.dependencies import get_health_repo_optional


class McpToolStates:
    def __init__(self, resources: ResourceService) -> None:
        self._resources = resources

    async def tool_states(self) -> Mapping[str, ToolState]:
        health = get_health_repo_optional()
        out: dict[str, ToolState] = {}
        for server in await self._resources.list(kind="mcp_server"):
            try:
                transport = MCPServerConfig.model_validate(server.config).transport.type
            except Exception:
                continue
            kind = ToolKind.CUSTOM_TOOLS if transport == "http_api" else ToolKind.MCP_SERVER
            status = ToolStatus.HEALTHY
            if not server.enabled:
                status = ToolStatus.OFF
            elif health is not None:
                row = await health.get(server.uid)
                if row is not None and row[0] == "failing":
                    status = ToolStatus.FAILING
            out[server.name] = ToolState(server.uid, server.name, kind, status)
        return out


__all__ = ["McpToolStates"]
