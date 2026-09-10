"""What tiering currently does to the catalogue, for the management UI.

Tool tiering lists a policy-dependent slice of the aggregated tools, which makes
"why can't the agent see tool X" one layer harder to answer. This module
answers it.

It reads the LAST-DISCOVERED catalogue from ``mcp_capability_preferences``
rather than querying every upstream live: this is a management read, and
cold-spawning every registered server to render a status panel would be far
more expensive than the question is worth. The decision it reports is computed
with the same pure policy the gateway applies, so it agrees with what an agent
sees as long as the catalogue has not changed since it was last discovered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from coffer.application.mcp.tiering_config import TieringConfig
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.namespace import prefix_tool
from coffer.domain.mcp.tool_tiering import select_listed_tools


@dataclass(frozen=True)
class ServerTiering:
    server: str
    total: int
    listed: int


@dataclass(frozen=True)
class TieringReport:
    enabled: bool
    budget: int
    window_days: int
    total: int
    listed: int
    hidden: int
    servers: list[ServerTiering]


async def build_tiering_report(
    *,
    resources: ResourceService,
    prefs: Any,
    invocations: Any,
    config: TieringConfig,
    clock: Callable[[], datetime],
) -> TieringReport:
    """Compute the current listing decision over the last-known catalogue."""
    catalogue: list[dict[str, Any]] = []
    per_server_total: dict[str, int] = {}

    for resource in await resources.list(kind="mcp_server", enabled=True):
        rows = await prefs.list_for(resource.id)
        keys = [r.capability_key for r in rows if r.capability_type == "tool" and r.enabled]
        per_server_total[resource.name] = len(keys)
        catalogue.extend(
            {"name": prefix_tool(resource.name, key), "description": "", "inputSchema": {}}
            for key in keys
        )

    if not config.enabled:
        return _report(config, catalogue, {t["name"] for t in catalogue}, per_server_total, 0)

    since = clock() - timedelta(days=config.window_days)
    try:
        usage = await invocations.usage_counts(since=since)
    except Exception:
        # Mirrors the gateway's fail-open rule: a broken statistics layer
        # reports "everything listed" rather than inventing hidden tools.
        return _report(config, catalogue, {t["name"] for t in catalogue}, per_server_total, 0)

    result = select_listed_tools(catalogue, usage, builtin_prefix="coffer__", budget=config.budget)
    listed_names = {t["name"] for t in result.listed}
    return _report(config, catalogue, listed_names, per_server_total, result.hidden_count)


def _report(
    config: TieringConfig,
    catalogue: list[dict[str, Any]],
    listed_names: set[str],
    per_server_total: dict[str, int],
    hidden: int,
) -> TieringReport:
    servers = [
        ServerTiering(
            server=name,
            total=total,
            listed=sum(
                1
                for t in catalogue
                if t["name"] in listed_names and t["name"].startswith(f"{name}__")
            ),
        )
        for name, total in sorted(per_server_total.items())
    ]
    return TieringReport(
        enabled=config.enabled,
        budget=config.budget,
        window_days=config.window_days,
        total=len(catalogue),
        listed=len(listed_names),
        hidden=hidden,
        servers=servers,
    )


__all__ = ["ServerTiering", "TieringReport", "build_tiering_report"]
