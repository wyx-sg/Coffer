"""Budget-driven selection of the tools the gateway lists (ADR-046).

Pure: no I/O, no infra import, kind-agnostic (importlinter Contracts 2b/5/6).
Given the aggregated ``tools/list`` entries and per-(server, tool) invocation
counts, decides which entries to list.

Everything not listed stays callable — tiering is a listing-side policy only.
``tools/call`` gates on capability preferences, never on list membership, and
``coffer__search_tools`` keeps ranking the full catalogue. That is what makes
the policy safe to apply by default.

Deterministic by construction: usage rank first, catalogue order as the tie
break, so an unchanged catalogue yields an identical slice every session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_BUDGET = 50
DEFAULT_WINDOW_DAYS = 90

# Separator between the server namespace and the upstream tool name, as
# applied by ``domain.mcp.namespace.prefix_tool``.
_NAMESPACE_SEP = "__"


@dataclass(frozen=True)
class TieringResult:
    """The listing decision. ``hidden_count`` counts upstream tools only."""

    listed: list[dict[str, Any]]
    hidden_count: int


def split_prefixed(name: str) -> tuple[str, str]:
    """``"jira__jira_get_issue"`` -> ``("jira", "jira_get_issue")``.

    Splits on the FIRST separator: a server name never contains it, an upstream
    tool name may.
    """
    server, sep, tool = name.partition(_NAMESPACE_SEP)
    if not sep:
        return "", name
    return server, tool


def select_listed_tools(
    tools: list[dict[str, Any]],
    usage: dict[tuple[str, str], int],
    *,
    builtin_prefix: str,
    budget: int,
) -> TieringResult:
    """Pick the tools to advertise in ``tools/list``.

    Coffer's own ``builtin_prefix`` tools are always listed and never consume
    the budget. Upstream tools at or under budget are all listed; over budget
    they are ranked by ``usage`` (descending) with catalogue order as the tie
    break, after reserving one slot per server so none disappears entirely.
    """
    builtins = [t for t in tools if str(t.get("name", "")).startswith(builtin_prefix)]
    upstream = [t for t in tools if not str(t.get("name", "")).startswith(builtin_prefix)]

    if len(upstream) <= budget:
        return TieringResult(listed=[*builtins, *upstream], hidden_count=0)

    order = {id(t): i for i, t in enumerate(upstream)}

    def _rank(tool: dict[str, Any]) -> tuple[int, int]:
        server, bare = split_prefixed(str(tool.get("name", "")))
        return (-usage.get((server, bare), 0), order[id(tool)])

    by_rank = sorted(upstream, key=_rank)

    # Reserve each server's best-ranked tool first, so a server whose tools are
    # all unused still reaches the agent. When servers outnumber the budget the
    # budget wins — but the slice then spans many servers instead of exhausting
    # one, which is the more useful failure.
    chosen: list[dict[str, Any]] = []
    seen_servers: set[str] = set()
    for tool in by_rank:
        server, _ = split_prefixed(str(tool.get("name", "")))
        if server in seen_servers:
            continue
        seen_servers.add(server)
        chosen.append(tool)
        if len(chosen) == budget:
            break

    # Fill whatever budget the per-server floor left, in pure rank order.
    if len(chosen) < budget:
        reserved = {id(t) for t in chosen}
        for tool in by_rank:
            if id(tool) in reserved:
                continue
            chosen.append(tool)
            if len(chosen) == budget:
                break

    picked = {id(t) for t in chosen}
    listed_upstream = [t for t in upstream if id(t) in picked]
    return TieringResult(
        listed=[*builtins, *listed_upstream],
        hidden_count=len(upstream) - len(listed_upstream),
    )


__all__ = [
    "DEFAULT_BUDGET",
    "DEFAULT_WINDOW_DAYS",
    "TieringResult",
    "select_listed_tools",
    "split_prefixed",
]
