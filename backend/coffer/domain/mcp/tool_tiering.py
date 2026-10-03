"""Budget-driven selection of the tools the gateway lists
(ADR tool-overload-tier-the-list-search-the-rest).

Pure: no I/O, no infra import, kind-agnostic (importlinter Contracts 2b/5/6).
Given the aggregated ``tools/list`` entries, per-(server, tool) invocation
counts and the person's per-tool exposure overrides, decides which entries to list.

Everything not listed stays callable — tiering is a listing-side policy only.
``tools/call`` gates on capability preferences, never on list membership, and
``coffer__search_tools`` keeps ranking the full catalogue. That is what makes
the policy safe to apply by default.

Deterministic by construction: usage rank first, catalogue order as the tie
break, so an unchanged catalogue yields an identical slice every session.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

DEFAULT_BUDGET = 50
DEFAULT_WINDOW_DAYS = 90

# Separator between the server namespace and the upstream tool name, as
# applied by ``domain.mcp.namespace.prefix_tool``.
_NAMESPACE_SEP = "__"


#: A tool's exposure setting. ``auto`` lets the budget decide by usage;
#: ``listed`` pins it into ``tools/list``; ``search`` leaves it to
#: ``coffer__search_tools`` only (spec mcp-gateway "Forward tools, resources and prompts").
ToolExposure = Literal["auto", "listed", "search"]
EXPOSURE_MODES: tuple[str, ...] = ("auto", "listed", "search")


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


def _pick_by_use(
    auto: list[dict[str, Any]], usage: dict[tuple[str, str], int], slots: int
) -> set[int]:
    """The ``slots`` best of ``auto`` by usage (catalogue order breaks ties),
    after reserving each server's best-ranked tool so none disappears wholly."""
    if slots <= 0:
        return set()
    order = {id(t): i for i, t in enumerate(auto)}

    def _rank(tool: dict[str, Any]) -> tuple[int, int]:
        server, bare = split_prefixed(str(tool.get("name", "")))
        return (-usage.get((server, bare), 0), order[id(tool)])

    by_rank = sorted(auto, key=_rank)
    chosen: list[dict[str, Any]] = []
    seen_servers: set[str] = set()
    for tool in by_rank:
        server, _ = split_prefixed(str(tool.get("name", "")))
        if server in seen_servers:
            continue
        seen_servers.add(server)
        chosen.append(tool)
        if len(chosen) == slots:
            break
    if len(chosen) < slots:
        reserved = {id(t) for t in chosen}
        for tool in by_rank:
            if id(tool) in reserved:
                continue
            chosen.append(tool)
            if len(chosen) == slots:
                break
    return {id(t) for t in chosen}


def select_listed_tools(
    tools: list[dict[str, Any]],
    usage: dict[tuple[str, str], int],
    *,
    builtin_prefix: str,
    budget: int,
    exposure: Mapping[str, str] | None = None,
) -> TieringResult:
    """Pick the tools to advertise in ``tools/list``.

    Coffer's own ``builtin_prefix`` tools are always listed and never consume
    the budget. ``exposure`` maps a namespaced tool name to the person's
    override: ``listed`` is always listed (and takes a slot of the budget),
    ``search`` never is. The remaining (``auto``) tools at or under the
    remaining budget are all listed; over it they are ranked by ``usage``
    (descending) with catalogue order as the tie break, after reserving one slot
    per server so none disappears entirely.
    """
    overrides = exposure or {}
    builtins = [t for t in tools if str(t.get("name", "")).startswith(builtin_prefix)]
    upstream = [t for t in tools if not str(t.get("name", "")).startswith(builtin_prefix)]

    def _mode(tool: dict[str, Any]) -> str:
        return overrides.get(str(tool.get("name", "")), "auto")

    pinned = {id(t) for t in upstream if _mode(t) == "listed"}
    auto = [t for t in upstream if _mode(t) == "auto"]
    slots = max(0, budget - len(pinned))
    picked = pinned | (
        {id(t) for t in auto} if len(auto) <= slots else _pick_by_use(auto, usage, slots)
    )
    listed_upstream = [t for t in upstream if id(t) in picked]
    return TieringResult(
        listed=[*builtins, *listed_upstream],
        hidden_count=len(upstream) - len(listed_upstream),
    )


__all__ = [
    "DEFAULT_BUDGET",
    "DEFAULT_WINDOW_DAYS",
    "EXPOSURE_MODES",
    "TieringResult",
    "ToolExposure",
    "select_listed_tools",
    "split_prefixed",
]
