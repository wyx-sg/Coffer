"""McpStdioLaunchers: the launcher each enabled stdio server starts with."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from coffer.application.mcp.stdio_launchers import McpStdioLaunchers, StdioLauncher


class _Server:
    def __init__(self, uid: str, name: str, config: dict[str, Any]) -> None:
        self.uid, self.name, self.config = uid, name, config


class _Resources:
    def __init__(self, servers: list[_Server]) -> None:
        self.servers = servers
        self.asked: list[tuple[str | None, bool | None]] = []

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> Sequence[Any]:
        self.asked.append((kind, enabled))
        return self.servers


async def test_only_stdio_servers_name_a_launcher() -> None:
    stdio = {"transport": {"type": "stdio", "command": "uvx", "args": ["mcp-server-duckdb"]}}
    http = {"transport": {"type": "http", "url": "https://example.test/mcp"}}
    resources = _Resources(
        [
            _Server("u1", "duckdb", stdio),
            _Server("u2", "remote", http),
            _Server("u3", "broken", {"transport": "nope"}),
        ]
    )
    got = await McpStdioLaunchers(resources).stdio_launchers()
    assert got == [StdioLauncher("u1", "duckdb", "uvx")]
    assert resources.asked == [("mcp_server", True)]
