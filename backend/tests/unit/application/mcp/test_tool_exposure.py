"""The effective exposure of a server's tools and why (spec mcp-gateway
"Choose how each tool is exposed"), with a fake invocation log."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.mcp.tiering_config import TieringConfig
from coffer.application.mcp.tiering_split import tiering_split


class _Invocations:
    def __init__(self, counts: dict[tuple[str, str], int]) -> None:
        self._counts = counts

    async def usage_counts(self, *, since: datetime) -> dict[tuple[str, str], int]:
        return self._counts


def _clock() -> datetime:
    return datetime(2026, 10, 2, tzinfo=UTC)


def _by_tool(split) -> dict[str, tuple[str, str, str]]:
    return {s.tool: (s.mode, s.effective, s.reason) for s in split.tools}


async def _split(counts, exposure, *, budget=2, enabled=True):
    return await tiering_split(
        {"smart": ["a", "b", "c", "d"]},
        "smart",
        invocations=_Invocations(counts),
        config=TieringConfig(enabled=enabled, budget=budget, window_days=30),
        clock=_clock,
        exposure=exposure,
    )


@pytest.mark.asyncio
async def test_auto_lists_the_most_used_and_says_why():
    split = await _split({("smart", "c"): 5, ("smart", "d"): 4}, {})

    assert _by_tool(split) == {
        "a": ("auto", "search", "low_use"),
        "b": ("auto", "search", "low_use"),
        "c": ("auto", "listed", "top_by_use"),
        "d": ("auto", "listed", "top_by_use"),
    }


@pytest.mark.asyncio
async def test_overrides_take_precedence_over_usage():
    split = await _split(
        {("smart", "c"): 5, ("smart", "d"): 4}, {"smart__a": "listed", "smart__c": "search"}
    )

    states = _by_tool(split)
    assert states["a"] == ("listed", "listed", "pinned")
    assert states["c"] == ("search", "search", "search_only")
    assert states["d"] == ("auto", "listed", "top_by_use")
    assert split.listed == ["a", "d"]
    assert split.behind_search == ["b", "c"]


@pytest.mark.asyncio
async def test_everything_fitting_the_budget_is_within_budget_not_top_by_use():
    split = await _split({}, {"smart__d": "search"}, budget=10)

    states = _by_tool(split)
    assert states["a"] == ("auto", "listed", "within_budget")
    assert states["d"] == ("search", "search", "search_only")


@pytest.mark.asyncio
async def test_with_tiering_off_everything_is_listed():
    split = await _split({}, {"smart__d": "search"}, enabled=False)

    assert all(effective == "listed" for _, effective, _ in _by_tool(split).values())
