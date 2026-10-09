"""A small real MCP server for the docs images.

    demo_mcp_server.py NAME TOOL:DESCRIPTION [TOOL:DESCRIPTION ...]

Each tool answers with a fixed line. It exists so the demo workspace's servers
list tools with real descriptions; the test fixture server describes every tool
as "fake tool".
"""

from __future__ import annotations

import sys

from mcp.server.mcpserver import MCPServer


def main(argv: list[str]) -> None:
    name, specs = argv[0], argv[1:]
    server = MCPServer(name)
    for spec in specs:
        tool, _, description = spec.partition(":")

        def handler(tool: str = tool) -> str:
            return f"{tool}: ok"

        server.add_tool(handler, name=tool, description=description)
    server.run("stdio")


if __name__ == "__main__":
    main(sys.argv[1:])
