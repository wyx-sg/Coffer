"""Spool ingest: cost at ingest, idempotent replay, rollup sums, malformed lines."""

from __future__ import annotations

from datetime import UTC, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from coffer.application.usage.ingest import UsageIngestService
from coffer.application.usage.ports import FailoverEvent
from coffer.domain.usage.pricing import ModelPrice
from coffer.infrastructure.persistence.usage_models import UsageDailyModel, UsageRequestModel
from coffer.infrastructure.persistence.usage_repo import SqlAlchemyUsageRepo
from coffer.infrastructure.usage.bundled_prices import load_bundled_prices
from coffer.infrastructure.usage.spool_reader import FileSpoolReader, default_spool_dir

from .conftest import NOW, FakePrices, record, write_spool


def _service(sm, spool: Path, prices: FakePrices | None = None) -> UsageIngestService:  # type: ignore[no-untyped-def]
    return UsageIngestService(
        repo=SqlAlchemyUsageRepo(sm),
        spool=FileSpoolReader(spool),
        prices=prices or FakePrices(),
        tz=UTC,
    )


async def _count(sm, model) -> int:  # type: ignore[no-untyped-def]
    async with sm() as s:
        return int((await s.execute(select(func.count()).select_from(model))).scalar_one())


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="replaying a spool file writes nothing twice",
)
async def test_replaying_the_same_spool_file_writes_nothing_twice(sm, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    spool = tmp_path / "spool"
    lines = [record(1), record(2)]
    write_spool(spool, "a.jsonl", lines)
    svc = _service(sm, spool)

    first = await svc.ingest_once()
    assert (first.files, first.inserted, first.duplicates) == (1, 2, 0)
    assert not (spool / "a.jsonl").exists()  # deleted only after the commit

    # The daemon crashed between commit and delete: the same file comes back.
    write_spool(spool, "a.jsonl", lines)
    second = await svc.ingest_once()
    assert (second.inserted, second.duplicates) == (0, 2)

    assert await _count(sm, UsageRequestModel) == 2
    async with sm() as s:
        (daily,) = (await s.execute(select(UsageDailyModel))).scalars().all()
    assert daily.requests == 2
    assert daily.input_tokens == 2000
    assert daily.cache_read_tokens == 4000


async def test_rollup_sums_per_day_agent_connection_and_model(sm, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    spool = tmp_path / "spool"
    write_spool(
        spool,
        "a.jsonl",
        [
            record(1),
            record(2, output_tokens=1500),
            record(3, model="claude-opus-4-6"),
            record(4, agent_uid=None, agent_type=None, connection_uid=None),
            record(
                5,
                usage_known=False,
                input_tokens=None,
                output_tokens=None,
                cache_read_tokens=None,
                reasoning_tokens=None,
                outcome="truncated",
            ),
        ],
    )
    await _service(sm, spool).ingest_once()
    async with sm() as s:
        rows = (await s.execute(select(UsageDailyModel))).scalars().all()
    by = {(r.agent_uid, r.connection_uid, r.model): r for r in rows}
    sonnet = by[("agent-claude", "conn-anthropic", "claude-sonnet-4-6")]
    # records 1, 2 and the unknown-usage 5 share the key; 5 adds a request, no tokens.
    assert (sonnet.requests, sonnet.unknown_requests) == (3, 1)
    assert sonnet.output_tokens == 2000
    assert sonnet.reasoning_tokens == 200
    # $3/MTok * 2000 + $0.30 * 4000 + $15 * 2000 = 0.006 + 0.0012 + 0.03
    assert sonnet.cost_usd == pytest.approx(0.0372)
    assert ("", "", "claude-sonnet-4-6") in by  # NULL grouping stored as ''
    assert by[("agent-claude", "conn-anthropic", "claude-opus-4-6")].requests == 1


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="stored cost names the price it used",
)
async def test_cost_is_stored_with_its_price_version(sm, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    spool = tmp_path / "spool"
    write_spool(
        spool,
        "a.jsonl",
        [
            record(1),
            record(2, model="acme-coder-1", wire="openai", connection_uid="conn-openai"),
            record(3, model="acme-coder-1", wire="openai", connection_uid="conn-relay"),
            record(4, usage_known=False, input_tokens=None, output_tokens=None),
        ],
    )
    prices = FakePrices({("conn-relay", "acme-coder-1"): ModelPrice(input=1.0, output=2.0)})
    await _service(sm, spool, prices).ingest_once()
    async with sm() as s:
        rows = {
            r.dedupe_key: r for r in (await s.execute(select(UsageRequestModel))).scalars().all()
        }
    assert rows["req_1"].price_version == load_bundled_prices().label
    assert rows["req_1"].price_version.startswith("bundled:genai-prices@")
    assert rows["req_1"].cost_usd == pytest.approx(0.0111)  # 3*1000 + 0.3*2000 + 15*500
    # An unknown model is flagged unpriced, never priced at zero.
    assert (rows["req_2"].unpriced, rows["req_2"].cost_usd) == (True, None)
    assert rows["req_3"].price_version == "override:conn-relay"
    assert rows["req_3"].cost_usd == pytest.approx((1000 + 2000) * 1.0 / 1e6 + 500 * 2.0 / 1e6)
    # Unknown usage carries no cost and is not "unpriced".
    assert (rows["req_4"].cost_usd, rows["req_4"].unpriced) == (None, False)
    async with sm() as s:
        daily = (await s.execute(select(UsageDailyModel))).scalars().all()
    assert sum(d.unpriced_requests for d in daily) == 1


async def test_malformed_lines_are_skipped_and_part_files_never_read(sm, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    spool = tmp_path / "spool"
    write_spool(spool, "a.jsonl", [record(1), "not json", '{"dedupe_key": "x"}'])
    write_spool(spool, "b.jsonl.part", [record(2)])
    result = await _service(sm, spool).ingest_once()
    assert (result.files, result.inserted, result.malformed) == (1, 1, 2)
    assert (spool / "b.jsonl.part").exists()


def test_spool_dir_honours_the_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("COFFER_PROXY_SPOOL_DIR", str(tmp_path / "s"))
    assert default_spool_dir() == tmp_path / "s"
    assert FileSpoolReader(tmp_path / "missing").completed() == []


class _Failovers:
    def __init__(self) -> None:
        self.events: list[FailoverEvent] = []

    async def failed_over(self, event: FailoverEvent) -> None:
        self.events.append(event)


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a failover is logged with where the request went",
)
async def test_a_failover_names_the_provider_that_answered(sm, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    spool = tmp_path / "spool"
    later = NOW + timedelta(milliseconds=40)
    write_spool(
        spool,
        "a.jsonl",
        [
            record(
                1,
                relay_id="rel-1",
                connection_uid="conn-a",
                member="Primary",
                status=503,
                outcome="upstream_error",
                failed_over=True,
                usage_known=False,
                input_tokens=None,
                output_tokens=None,
            ),
            record(2, relay_id="rel-1", connection_uid="conn-b", member="Spare", started_at=later),
            record(3, relay_id="rel-2"),
        ],
    )
    log = _Failovers()
    svc = UsageIngestService(
        repo=SqlAlchemyUsageRepo(sm),
        spool=FileSpoolReader(spool),
        prices=FakePrices(),
        failovers=log,
        tz=UTC,
    )
    await svc.ingest_once()
    assert len(log.events) == 1
    event = log.events[0]
    assert (event.from_uid, event.from_name, event.to_uid, event.to_name) == (
        "conn-a",
        "Primary",
        "conn-b",
        "Spare",
    )
    assert (event.reason, event.model, event.agent_type) == (
        "status 503",
        "claude-sonnet-4-6",
        "claude_code",
    )
    # Usage is metered on the provider that actually answered.
    async with sm() as s:
        rows = {r.dedupe_key: r for r in (await s.execute(select(UsageRequestModel))).scalars()}
    assert rows["req_2"].connection_uid == "conn-b" and rows["req_2"].cost_usd is not None
    assert rows["req_1"].cost_usd is None

    # A replayed file logs nothing twice.
    write_spool(spool, "a.jsonl", [record(1, relay_id="rel-1", failed_over=True)])
    await svc.ingest_once()
    assert len(log.events) == 1
