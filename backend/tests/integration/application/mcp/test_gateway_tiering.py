"""Tiering as the gateway applies it — including the two fail-open paths.

Tool tiering is only safe to enable by default because it fails open in both
directions: tiering switched off, or a usage query that raises, must list
everything. A broken statistics layer must never be able to hide tools.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.mcp.gateway_tiering import apply_tiering
from coffer.application.mcp.tiering_config import TieringConfig


class _Invocations:
    def __init__(self, counts=None, *, fail=False):
        self._counts = counts or {}
        self._fail = fail
        self.since_seen: datetime | None = None

    async def usage_counts(self, *, since):
        if self._fail:
            raise RuntimeError("db is down")
        self.since_seen = since
        return self._counts


def _tools(n: int, server: str = "jira") -> list[dict]:
    return [{"name": f"{server}__t{i}", "description": "", "inputSchema": {}} for i in range(n)]


def _clock() -> datetime:
    return datetime(2026, 9, 9, tzinfo=UTC)


@pytest.mark.asyncio
async def test_tiering_trims_to_budget():
    tools = [{"name": "coffer__recall", "description": "", "inputSchema": {}}, *_tools(80)]
    cfg = TieringConfig(enabled=True, budget=10, window_days=90)

    result = await apply_tiering(tools, invocations=_Invocations(), config=cfg, clock=_clock)

    assert len(result.listed) == 11  # 1 builtin + 10 upstream
    assert result.hidden_count == 70


@pytest.mark.asyncio
async def test_disabled_config_lists_everything():
    tools = _tools(80)
    cfg = TieringConfig(enabled=False, budget=10, window_days=90)

    result = await apply_tiering(tools, invocations=_Invocations(), config=cfg, clock=_clock)

    assert len(result.listed) == 80
    assert result.hidden_count == 0


@pytest.mark.asyncio
async def test_usage_query_failure_degrades_to_listing_everything():
    tools = _tools(80)
    cfg = TieringConfig(enabled=True, budget=10, window_days=90)

    result = await apply_tiering(
        tools, invocations=_Invocations(fail=True), config=cfg, clock=_clock
    )

    assert len(result.listed) == 80
    assert result.hidden_count == 0


@pytest.mark.asyncio
async def test_window_is_derived_from_config():
    tools = _tools(80)
    cfg = TieringConfig(enabled=True, budget=10, window_days=7)
    inv = _Invocations()

    await apply_tiering(tools, invocations=inv, config=cfg, clock=_clock)

    assert inv.since_seen is not None
    assert (_clock() - inv.since_seen).days == 7


@pytest.mark.asyncio
async def test_usage_counts_drive_the_selection():
    tools = _tools(80)
    cfg = TieringConfig(enabled=True, budget=2, window_days=90)
    inv = _Invocations({("jira", "t70"): 9, ("jira", "t71"): 8})

    result = await apply_tiering(tools, invocations=inv, config=cfg, clock=_clock)

    assert [t["name"] for t in result.listed] == ["jira__t70", "jira__t71"]


@pytest.mark.asyncio
async def test_search_tools_is_never_hidden():
    """The escape hatch must survive its own policy."""
    tools = [
        {"name": "coffer__search_tools", "description": "", "inputSchema": {}},
        *_tools(200),
    ]
    cfg = TieringConfig(enabled=True, budget=1, window_days=90)

    result = await apply_tiering(tools, invocations=_Invocations(), config=cfg, clock=_clock)

    assert "coffer__search_tools" in [t["name"] for t in result.listed]
