"""The launcher each enabled stdio MCP server starts with, for the CLIs page
(spec skill-manager "Check every required command where the agent runs").

The skill kind's required-command check lists these launchers beside the
commands skills declare, so a server's ``uvx`` shows up as ``uv`` needed by
that server. This module reads the MCP side; the composition root hands it
to the check, which describes what it wants structurally and never imports
this kind.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Resource

KIND = "mcp_server"


class McpServersPort(Protocol):
    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> Sequence[Resource]: ...


@dataclass(frozen=True)
class StdioLauncher:
    server_uid: str
    server_name: str
    launcher: str


class McpStdioLaunchers:
    """Enabled stdio servers only: a server that is off is not expected to
    start, and an HTTP server has no launcher."""

    def __init__(self, resources: McpServersPort) -> None:
        self._resources = resources

    async def stdio_launchers(self) -> Sequence[StdioLauncher]:
        out: list[StdioLauncher] = []
        for server in await self._resources.list(kind=KIND, enabled=True):
            try:
                parsed = MCPServerConfig.model_validate(server.config)
            except Exception:
                continue
            if parsed.transport.type == "stdio" and parsed.transport.command:
                out.append(StdioLauncher(server.uid, server.name, parsed.transport.command))
        return out


__all__ = ["McpStdioLaunchers", "StdioLauncher"]
