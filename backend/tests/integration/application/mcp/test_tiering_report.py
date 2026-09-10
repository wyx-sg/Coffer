"""The management-side view of what tiering is doing to the catalogue.

Tool tiering makes tools/list policy-dependent, so this report is the answer to
"why can't the agent see tool X". It must agree with the gateway's decision and
must never invent hidden tools when it cannot compute one.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.mcp.tiering_config import TieringConfig
from coffer.application.mcp.tiering_report import build_tiering_report


class _Resource:
    def __init__(self, rid: int, name: str):
        self.id = rid
        self.name = name


class _Resources:
    def __init__(self, servers: dict[str, int]):
        self._servers = servers

    async def list(self, *, kind: str, enabled: bool):
        assert kind == "mcp_server"
        assert enabled is True
        return [_Resource(i, name) for i, name in enumerate(self._servers, start=1)]


class _Row:
    def __init__(self, key: str):
        self.capability_key = key
        self.capability_type = "tool"
        self.enabled = True


class _Prefs:
    def __init__(self, servers: dict[str, int]):
        self._by_id = {
            i: [_Row(f"t{n}") for n in range(count)]
            for i, count in enumerate(servers.values(), start=1)
        }

    async def list_for(self, resource_id: int):
        return self._by_id[resource_id]


class _Invocations:
    def __init__(self, counts=None, *, fail=False):
        self._counts = counts or {}
        self._fail = fail

    async def usage_counts(self, *, since):
        if self._fail:
            raise RuntimeError("db is down")
        return self._counts


def _clock() -> datetime:
    return datetime(2026, 9, 9, tzinfo=UTC)


async def _report(servers, config, invocations=None):
    return await build_tiering_report(
        resources=_Resources(servers),
        prefs=_Prefs(servers),
        invocations=invocations or _Invocations(),
        config=config,
        clock=_clock,
    )


@pytest.mark.asyncio
async def test_under_budget_reports_nothing_hidden():
    report = await _report(
        {"jira": 10, "seatalk": 5}, TieringConfig(enabled=True, budget=50, window_days=90)
    )

    assert report.total == 15
    assert report.listed == 15
    assert report.hidden == 0


@pytest.mark.asyncio
async def test_over_budget_reports_the_split():
    report = await _report({"jira": 80}, TieringConfig(enabled=True, budget=10, window_days=90))

    assert report.total == 80
    assert report.listed == 10
    assert report.hidden == 70


@pytest.mark.asyncio
async def test_per_server_counts_add_up():
    report = await _report(
        {"jira": 60, "seatalk": 5}, TieringConfig(enabled=True, budget=10, window_days=90)
    )

    assert sum(s.total for s in report.servers) == report.total
    assert sum(s.listed for s in report.servers) == report.listed
    # The per-server floor keeps seatalk visible even though jira dominates.
    assert next(s for s in report.servers if s.server == "seatalk").listed >= 1


@pytest.mark.asyncio
async def test_disabled_tiering_reports_everything_listed():
    report = await _report({"jira": 80}, TieringConfig(enabled=False, budget=10, window_days=90))

    assert report.enabled is False
    assert report.listed == 80
    assert report.hidden == 0


@pytest.mark.asyncio
async def test_usage_failure_never_invents_hidden_tools():
    report = await _report(
        {"jira": 80},
        TieringConfig(enabled=True, budget=10, window_days=90),
        invocations=_Invocations(fail=True),
    )

    assert report.listed == 80
    assert report.hidden == 0


@pytest.mark.asyncio
async def test_no_servers_is_an_empty_report():
    report = await _report({}, TieringConfig(enabled=True, budget=50, window_days=90))

    assert report.total == 0
    assert report.servers == []
