"""Kind-agnostic registry of Coffer's own MCP tools.

These tools are exposed through Coffer's MCP gateway under the reserved
prefix `coffer__`, alongside upstream-MCP-server tools. Each kind contributes
its own tools at composition-root time; the gateway only sees the kind-agnostic
`BuiltinTool` interface.

Contract 6 is honoured: this module imports no kind-specific code. Per-kind
modules live under `application/<kind>/builtin_tools.py` and are wired into
this registry by the composition root.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BuiltinTool:
    """An MCP tool that lives inside Coffer's own daemon.

    `name` is the *bare* tool name. The gateway prefixes it with `coffer__`
    when listing and accepts the prefixed form when dispatching.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


# Reserved prefix used to namespace Coffer's own tools so they cannot
# collide with upstream-server tools (which follow `<server>__<tool>`).
COFFER_TOOL_PREFIX = "coffer__"


class BuiltinToolRegistry:
    """In-process registry. Populated at startup; read-only after that."""

    def __init__(self) -> None:
        self._tools: dict[str, BuiltinTool] = {}

    def register(self, tool: BuiltinTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate built-in tool: {tool.name!r}")
        if tool.name.startswith(COFFER_TOOL_PREFIX):
            raise ValueError(
                "built-in tool names are stored unprefixed; the gateway "
                "adds the coffer__ prefix on list"
            )
        self._tools[tool.name] = tool

    def list(self) -> list[BuiltinTool]:
        return list(self._tools.values())

    def get(self, prefixed_name: str) -> BuiltinTool | None:
        if not prefixed_name.startswith(COFFER_TOOL_PREFIX):
            return None
        bare = prefixed_name[len(COFFER_TOOL_PREFIX) :]
        return self._tools.get(bare)

    def is_builtin(self, prefixed_name: str) -> bool:
        return self.get(prefixed_name) is not None

    def __len__(self) -> int:
        return len(self._tools)
