"""Which of one server's tools the gateway lists and which it leaves to search.

The MCP server page's "Tools reach agents" (spec mcp-gateway "Forward tools,
resources and prompts"). The gateway decides per session from a live,
per-session discovery cache that a page read cannot see, so this runs the SAME
policy (``gateway_tiering.apply_tiering``, fail-open included) over the tool
lists discovery last saved for every enabled server on this machine. It is a
machine-wide view — the catalogue of every enabled server, not the slice one
agent's reach sees — which is what "most behind search" means to the person
reading the page.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from coffer.application.mcp.gateway_tiering import apply_tiering
from coffer.application.mcp.ports import MCPInvocationRepoPort
from coffer.application.mcp.tiering_config import TieringConfig


@dataclass(frozen=True)
class TieringSplit:
    enabled: bool
    budget: int
    catalogue_size: int
    listed_count: int
    listed: list[str]
    behind_search: list[str]


async def tiering_split(
    catalogue: Mapping[str, Sequence[str]],
    server: str,
    *,
    invocations: MCPInvocationRepoPort,
    config: TieringConfig,
    clock: Callable[[], datetime],
) -> TieringSplit:
    """Split ``server``'s tools in ``catalogue`` (server name → its enabled tools)."""
    tools = [{"name": f"{name}__{tool}"} for name, names in catalogue.items() for tool in names]
    result = await apply_tiering(tools, invocations=invocations, config=config, clock=clock)
    listed_names = {str(t["name"]) for t in result.listed}
    own = catalogue.get(server, [])
    listed = [tool for tool in own if f"{server}__{tool}" in listed_names]
    behind = [tool for tool in own if f"{server}__{tool}" not in listed_names]
    return TieringSplit(
        enabled=config.enabled,
        budget=config.budget,
        catalogue_size=len(tools),
        listed_count=len(tools) - result.hidden_count,
        listed=listed,
        behind_search=behind,
    )


__all__ = ["TieringSplit", "tiering_split"]
