"""Usage summaries (model / agent / day) and the per-request cursor."""

from __future__ import annotations

from datetime import UTC, date, timedelta
from pathlib import Path

import pytest

from coffer.application.usage.ingest import UsageIngestService
from coffer.application.usage.ports import RequestFilters
from coffer.application.usage.query import GroupBy, SummaryFilters, UsageQueryService
from coffer.domain.pagination import CursorInvalid
from coffer.domain.usage.ranges import InvalidRange
from coffer.infrastructure.persistence.usage_repo import SqlAlchemyUsageRepo
from coffer.infrastructure.usage.spool_reader import FileSpoolReader

from .conftest import NOW, FakeClock, FakeNames, FakePrices, record, write_spool


async def _seed(sm, tmp_path: Path) -> UsageQueryService:  # type: ignore[no-untyped-def]
    spool = tmp_path / "spool"
    write_spool(
        spool,
        "a.jsonl",
        [
            record(1),
            record(2, started_at=NOW - timedelta(days=2)),
            record(3, model="claude-opus-4-6", agent_uid="agent-2"),
            record(
                4,
                model="acme-coder-1",
                wire="openai",
                connection_uid="conn-openai",
                agent_uid="agent-codex",
                agent_type="codex",
            ),
            record(
                5,
                usage_known=False,
                input_tokens=None,
                output_tokens=None,
                cache_read_tokens=None,
                reasoning_tokens=None,
                outcome="truncated",
            ),
            record(6, started_at=NOW - timedelta(days=40)),
        ],
    )
    repo = SqlAlchemyUsageRepo(sm)
    await UsageIngestService(
        repo=repo, spool=FileSpoolReader(spool), prices=FakePrices(), tz=UTC
    ).ingest_once()
    return UsageQueryService(
        repo=repo,
        connection_names=FakeNames({"conn-anthropic": "Anthropic"}),
        clock=FakeClock(),
        tz=UTC,
    )


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="usage by model names the connection",
)
async def test_summary_by_model_carries_the_connection_name(sm, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    svc = await _seed(sm, tmp_path)
    summary = await svc.summary("today", group_by=GroupBy.MODEL)
    assert summary.cost_is_estimate is True
    rows = {r.model: r for r in summary.rows}
    sonnet = rows["claude-sonnet-4-6"]
    assert (sonnet.connection_uid, sonnet.connection_name) == ("conn-anthropic", "Anthropic")
    assert sonnet.totals.requests == 2  # record 1 + the unknown-usage record 5
    assert sonnet.totals.unknown_usage_requests == 1
    assert rows["acme-coder-1"].totals.unpriced_requests == 1
    assert rows["acme-coder-1"].connection_name is None  # connection gone: uid only
    assert summary.totals.requests == 4
    assert summary.totals.unpriced_requests == 1
    assert summary.totals.cost_usd == pytest.approx(sum(r.totals.cost_usd for r in summary.rows))


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="usage by agent and by day",
)
async def test_summary_by_agent_and_by_day(sm, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    svc = await _seed(sm, tmp_path)
    by_agent = await svc.summary("7d", group_by="agent")
    agents = {r.agent_uid: r.totals.requests for r in by_agent.rows}
    assert agents == {"agent-claude": 3, "agent-2": 1, "agent-codex": 1}

    by_day = await svc.summary("7d", group_by="day")
    assert [r.day for r in by_day.rows] == [
        (NOW.date() - timedelta(days=d)).isoformat() for d in range(6, -1, -1)
    ]  # every day of the span, quiet days as zero
    counts = {r.day: r.totals.requests for r in by_day.rows}
    assert counts[NOW.date().isoformat()] == 4
    assert counts[(NOW.date() - timedelta(days=2)).isoformat()] == 1

    month = await svc.summary("custom", start=date(2026, 8, 1), end=date(2026, 8, 31))
    assert month.totals.requests == 1  # record 6, 40 days back
    with pytest.raises(InvalidRange):
        await svc.summary("custom", start=date(2026, 8, 2))


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the last 24 hours is a rolling window",
)
async def test_the_last_24_hours_is_a_rolling_window(sm, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    spool = tmp_path / "spool"
    write_spool(
        spool,
        "a.jsonl",
        [
            record(1, started_at=NOW - timedelta(hours=2)),
            record(2, started_at=NOW - timedelta(hours=23)),
            record(3, started_at=NOW - timedelta(hours=25)),
        ],
    )
    repo = SqlAlchemyUsageRepo(sm)
    await UsageIngestService(
        repo=repo, spool=FileSpoolReader(spool), prices=FakePrices(), tz=UTC
    ).ingest_once()
    svc = UsageQueryService(repo=repo, connection_names=FakeNames({}), clock=FakeClock(), tz=UTC)

    summary = await svc.summary("24h")
    assert summary.totals.requests == 2
    # The 25-hour-old request is on the same local day as the 23-hour-old one's
    # neighbour yesterday, which the daily rollup would have counted whole.
    assert (await svc.summary("7d")).totals.requests == 3


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="usage narrowed to one agent and one provider",
)
async def test_summary_filters_and_the_agents_behind_each_row(sm, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    svc = await _seed(sm, tmp_path)
    codex = await svc.summary("today", filters=SummaryFilters(agent_type="codex"))
    assert [r.model for r in codex.rows] == ["acme-coder-1"]
    assert codex.totals.requests == 1
    anthropic = await svc.summary(
        "today", group_by="agent", filters=SummaryFilters(connection_uid="conn-anthropic")
    )
    assert anthropic.totals.requests == 3
    assert {r.agent_type for r in anthropic.rows} == {"claude_code"}
    both = SummaryFilters(agent_type="codex", connection_uid="conn-anthropic")
    assert (await svc.summary("today", filters=both)).totals.requests == 0

    by_model = {r.model: r for r in (await svc.summary("today")).rows}
    assert by_model["claude-sonnet-4-6"].agent_types == ("claude_code",)
    by_day = {r.day: r for r in (await svc.summary("7d", group_by="day")).rows}
    assert by_day[NOW.date().isoformat()].agent_types == ("claude_code", "codex")
    assert by_day[(NOW.date() - timedelta(days=1)).isoformat()].agent_types == ()


async def test_requests_page_newest_first_by_cursor(sm, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    svc = await _seed(sm, tmp_path)
    first = await svc.requests(limit=4)
    assert len(first.items) == 4 and first.next_cursor is not None
    second = await svc.requests(limit=4, cursor=first.next_cursor)
    seen = [r.record.dedupe_key for r in first.items + second.items]
    assert len(seen) == 6 and len(set(seen)) == 6
    assert second.next_cursor is None
    assert seen[-1] == "req_6"  # oldest last
    starts = [r.record.started_at for r in first.items + second.items]
    assert starts == sorted(starts, reverse=True)

    only_codex = await svc.requests(filters=RequestFilters(agent_uid="agent-codex"))
    assert [r.record.model for r in only_codex.items] == ["acme-coder-1"]
    with pytest.raises(CursorInvalid):
        await svc.requests(filters=RequestFilters(model="x"), cursor=first.next_cursor)
