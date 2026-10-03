"""How each tool is exposed to agents: the person's override and the reason
for the effective state (spec mcp-gateway "Forward tools, resources and prompts").

``auto`` (the default) leaves the decision to the budget: the most-used tools
stay listed in ``tools/list``, the rest are reached through
``coffer__search_tools``. ``listed`` pins a tool into the list, ``search``
demotes it. The override is the person's, per (server, tool), and lives in the
server's ``mcp-preferences`` vault document.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from coffer.application.mcp.ports import MCPCapabilityPreferenceRepoPort
from coffer.domain.mcp.namespace import prefix_tool
from coffer.domain.mcp.tool_tiering import ToolExposure
from coffer.domain.resource import Resource

Effective = Literal["listed", "search"]
#: Why a tool is in its effective state.
Reason = Literal["pinned", "search_only", "within_budget", "top_by_use", "low_use"]


@dataclass(frozen=True)
class ToolExposureState:
    tool: str
    mode: ToolExposure  # what the person set
    effective: Effective
    reason: Reason


async def exposure_overrides(
    prefs: MCPCapabilityPreferenceRepoPort, servers: Sequence[Resource]
) -> dict[str, str]:
    """Namespaced tool name -> ``listed`` | ``search`` over ``servers``."""
    out: dict[str, str] = {}
    for server in servers:
        for tool, mode in prefs.exposure_for(server.uid).items():
            out[prefix_tool(server.name, tool)] = mode
    return out


def explain(
    server: str,
    tools: Sequence[str],
    overrides: dict[str, str],
    listed: set[str],
    *,
    auto_hidden: bool,
) -> list[ToolExposureState]:
    """The effective state of ``tools`` of ``server`` and why.

    ``listed`` holds the namespaced names the policy lists; ``auto_hidden`` is
    whether the budget left any ``auto`` tool unlisted (so "top by use" is
    earned rather than everything simply fitting).
    """
    states: list[ToolExposureState] = []
    for tool in tools:
        name = prefix_tool(server, tool)
        mode: ToolExposure = (
            "listed"
            if overrides.get(name) == "listed"
            else ("search" if overrides.get(name) == "search" else "auto")
        )
        is_listed = name in listed
        reason: Reason
        if mode == "listed":
            reason = "pinned"
        elif mode == "search" and not is_listed:
            reason = "search_only"
        elif not is_listed:
            reason = "low_use"
        else:
            reason = "top_by_use" if auto_hidden else "within_budget"
        states.append(ToolExposureState(tool, mode, "listed" if is_listed else "search", reason))
    return states


__all__ = ["Effective", "Reason", "ToolExposureState", "explain", "exposure_overrides"]
