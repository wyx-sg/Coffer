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

from coffer.domain.features import get_feature


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
    #: The experimental feature that owns this tool, or ``None`` for a tool
    #: that is always there. While the feature is off the tool is absent from
    #: the list and a call to it answers exactly as a call to an unknown tool
    #: (spec experimental-features "Close every surface of a switched-off
    #: feature").
    feature: str | None = None


# Reserved prefix used to namespace Coffer's own tools so they cannot
# collide with upstream-server tools (which follow `<server>__<tool>`).
COFFER_TOOL_PREFIX = "coffer__"


class BuiltinToolRegistry:
    """In-process registry. Populated at startup; read-only after that.

    ``feature_enabled`` answers whether an experimental feature is on right
    now. It is asked on every read, so a switch takes effect without a restart:
    a tool whose feature is off is neither listed nor found, and every reader
    (the gateway's list and call, the chat session's tool set) sees exactly the
    tools that are there. Without it every tool is there.
    """

    def __init__(self, *, feature_enabled: Callable[[str], bool] | None = None) -> None:
        self._tools: dict[str, BuiltinTool] = {}
        self._feature_enabled = feature_enabled

    def _present(self, tool: BuiltinTool) -> bool:
        if tool.feature is None or self._feature_enabled is None:
            return True
        return self._feature_enabled(tool.feature)

    def register(self, tool: BuiltinTool) -> None:
        if tool.feature is not None:
            get_feature(tool.feature)  # an unregistered key is a wiring mistake
        if tool.name in self._tools:
            raise ValueError(f"duplicate built-in tool: {tool.name!r}")
        if tool.name.startswith(COFFER_TOOL_PREFIX):
            raise ValueError(
                "built-in tool names are stored unprefixed; the gateway "
                "adds the coffer__ prefix on list"
            )
        self._tools[tool.name] = tool

    def list(self) -> list[BuiltinTool]:
        return [tool for tool in self._tools.values() if self._present(tool)]

    def get(self, prefixed_name: str) -> BuiltinTool | None:
        if not prefixed_name.startswith(COFFER_TOOL_PREFIX):
            return None
        bare = prefixed_name[len(COFFER_TOOL_PREFIX) :]
        tool = self._tools.get(bare)
        if tool is None or not self._present(tool):
            return None
        return tool

    def is_builtin(self, prefixed_name: str) -> bool:
        return self.get(prefixed_name) is not None

    def __len__(self) -> int:
        return len(self.list())
