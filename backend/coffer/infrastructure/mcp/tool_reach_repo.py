"""Custom tools' reach overrides, on this machine only: ``local/tool-reach.json``.

Implements ``application.mcp.custom_tool_ports.ToolReachRepoPort``. A custom
tool may narrow its group's reach to some agents (spec mcp-gateway "Switch off
or narrow one custom tool"); like every reach it is a fact about this machine
(ADR reach-is-machine-local-stored-by-uid-never-synced), so it is local state
beside ``local/reach.json`` and never in the group's vault file::

    {"<group uid>": {"<tool name>": ["<agent uid>", ...] | "all"}}

``"all"`` is the tool's own "every agent the group reaches", distinct from no
entry (same as the group) so an agent added later is included.

Keyed by the group's uid and the tool's name, so a group keeps its overrides
as its config changes. A tool with no entry reaches wherever its group does.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from coffer.application.mcp.custom_tool_ports import ToolReach
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore


def tool_reach_path(home: Path | None = None) -> Path:
    return local_root(home) / "tool-reach.json"


class MCPToolReachStore:
    """``ToolReachRepoPort`` over ``local/tool-reach.json``."""

    def __init__(self, path: Path | Callable[[], Path] = tool_reach_path) -> None:
        self._store = JsonStore(path)

    async def overrides_for(self, resource_uids: Sequence[str]) -> dict[str, dict[str, ToolReach]]:
        wanted = set(resource_uids)
        if not wanted:
            return {}
        out: dict[str, dict[str, ToolReach]] = {}
        for uid, tools in self._store.read().items():
            if uid not in wanted or not isinstance(tools, dict):
                continue
            kept: dict[str, ToolReach] = {}
            for tool, agents in tools.items():
                if agents == "all":
                    kept[str(tool)] = "all"
                elif isinstance(agents, list):
                    kept[str(tool)] = [str(a) for a in agents]
            if kept:
                out[uid] = kept
        return out

    async def set_override(self, resource_uid: str, tool: str, reach: ToolReach | None) -> None:
        def change(doc: dict[str, Any]) -> None:
            tools = doc.get(resource_uid)
            tools = dict(tools) if isinstance(tools, dict) else {}
            if reach is None:
                tools.pop(tool, None)
            else:
                tools[tool] = reach if reach == "all" else list(reach)
            if tools:
                doc[resource_uid] = tools
            else:
                doc.pop(resource_uid, None)

        self._store.update(change)

    async def delete_tools(self, resource_uid: str, tools: Sequence[str]) -> None:
        if not tools:
            return
        gone = set(tools)

        def change(doc: dict[str, Any]) -> None:
            current = doc.get(resource_uid)
            if not isinstance(current, dict):
                return
            kept = {t: a for t, a in current.items() if t not in gone}
            if kept:
                doc[resource_uid] = kept
            else:
                doc.pop(resource_uid, None)

        self._store.update(change)

    async def delete_group(self, resource_uid: str) -> None:
        def change(doc: dict[str, Any]) -> None:
            doc.pop(resource_uid, None)

        self._store.update(change)


__all__ = ["MCPToolReachStore", "tool_reach_path"]
