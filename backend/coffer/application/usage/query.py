"""Read usage back: summaries from the daily rollup, the per-request list, CSV
(ADR usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

A summary reads only ``usage_daily``, so it is cheap for any range the rollup
still holds (a year). Costs are ESTIMATES — computed at ingest from the price
version stored with each row — and every summary says so. Two counts keep the
totals honest: ``unknown_usage_requests`` (a stream cut before its usage
arrived; its tokens are not in the sums, not zero) and ``unpriced_requests``
(tokens known, but no price covered the model; they are in the token sums and
not in the cost).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, fields, replace
from datetime import date, timedelta, tzinfo
from enum import StrEnum

from coffer.application.usage.ingest import local_tz
from coffer.application.usage.ports import (
    Clock,
    ConnectionNames,
    DailyUsage,
    RequestFilters,
    StoredUsage,
    SystemClock,
    UsageRepo,
)
from coffer.domain.pagination import Page, decode_cursor, paginate, position_of, time_and_id
from coffer.domain.usage.ranges import DateRange, resolve_range

_REQUESTS_LIST = "usage_requests"


class GroupBy(StrEnum):
    MODEL = "model"
    AGENT = "agent"
    DAY = "day"


@dataclass(frozen=True)
class UsageTotals:
    """Summed counts over some set of rollup rows."""

    requests: int = 0
    unknown_usage_requests: int = 0
    unpriced_requests: int = 0
    input_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    web_search_requests: int = 0
    cost_usd: float = 0.0

    def plus(self, row: DailyUsage) -> UsageTotals:
        return UsageTotals(
            requests=self.requests + row.requests,
            unknown_usage_requests=self.unknown_usage_requests + row.unknown_requests,
            unpriced_requests=self.unpriced_requests + row.unpriced_requests,
            input_tokens=self.input_tokens + row.input_tokens,
            cache_write_5m_tokens=self.cache_write_5m_tokens + row.cache_write_5m_tokens,
            cache_write_1h_tokens=self.cache_write_1h_tokens + row.cache_write_1h_tokens,
            cache_read_tokens=self.cache_read_tokens + row.cache_read_tokens,
            output_tokens=self.output_tokens + row.output_tokens,
            reasoning_tokens=self.reasoning_tokens + row.reasoning_tokens,
            web_search_requests=self.web_search_requests + row.web_search_requests,
            cost_usd=self.cost_usd + row.cost_usd,
        )


@dataclass(frozen=True)
class SummaryRow:
    """One group of a summary. Which identity fields are set depends on the
    grouping: ``model`` + ``connection_*`` for model, ``agent_*`` for agent,
    ``day`` for day."""

    key: str
    totals: UsageTotals
    model: str | None = None
    connection_uid: str | None = None
    connection_name: str | None = None
    agent_uid: str | None = None
    agent_type: str | None = None
    day: str | None = None


@dataclass(frozen=True)
class UsageSummary:
    range: DateRange
    group_by: GroupBy
    rows: list[SummaryRow]
    totals: UsageTotals
    #: Always true: a stored cost is an estimate from a price table.
    cost_is_estimate: bool = True
    price_note: str = field(
        default="Costs are estimates from the price version stored with each request."
    )


def _group_key(group_by: GroupBy, row: DailyUsage) -> tuple[str | None, ...]:
    if group_by is GroupBy.MODEL:
        return (row.model, row.connection_uid)
    if group_by is GroupBy.AGENT:
        return (row.agent_uid, row.agent_type)
    return (row.day,)


def _days(span: DateRange) -> Iterable[date]:
    day = span.start
    while day <= span.end:
        yield day
        day += timedelta(days=1)


class UsageQueryService:
    def __init__(
        self,
        *,
        repo: UsageRepo,
        connection_names: ConnectionNames,
        clock: Clock | None = None,
        tz: tzinfo | None = None,
    ) -> None:
        self._repo = repo
        self._names = connection_names
        self._clock = clock or SystemClock()
        self._tz = tz or local_tz()

    def resolve(
        self, range_name: str, start: date | None = None, end: date | None = None
    ) -> DateRange:
        """The local-day span a range name means now (raises ``InvalidRange``)."""
        return resolve_range(range_name, now=self._clock.now(), tz=self._tz, start=start, end=end)

    async def summary(
        self,
        range_name: str = "today",
        *,
        start: date | None = None,
        end: date | None = None,
        group_by: GroupBy | str = GroupBy.MODEL,
    ) -> UsageSummary:
        span = self.resolve(range_name, start, end)
        grouping = GroupBy(group_by)
        daily = await self._repo.daily(span.start_day, span.end_day)
        groups: dict[tuple[str | None, ...], tuple[DailyUsage, UsageTotals]] = {}
        total = UsageTotals()
        for row in daily:
            key = _group_key(grouping, row)
            first, sums = groups.get(key, (row, UsageTotals()))
            groups[key] = (first, sums.plus(row))
            total = total.plus(row)
        if grouping is GroupBy.DAY:
            # Every day of the span, so a chart has no gaps: a quiet day is a 0.
            for day in _days(span):
                key = (day.isoformat(),)
                if key not in groups:
                    groups[key] = (DailyUsage(key[0], None, None, None, None), UsageTotals())
        rows = [self._row(grouping, first, sums) for first, sums in groups.values()]
        if grouping is GroupBy.MODEL:
            rows = await self._with_connection_names(rows)
        if grouping is GroupBy.DAY:
            rows.sort(key=lambda r: r.key)
        else:
            rows.sort(key=lambda r: (-r.totals.cost_usd, -r.totals.requests, r.key))
        return UsageSummary(range=span, group_by=grouping, rows=rows, totals=total)

    @staticmethod
    def _row(grouping: GroupBy, first: DailyUsage, sums: UsageTotals) -> SummaryRow:
        if grouping is GroupBy.MODEL:
            return SummaryRow(
                key=f"{first.model or ''}|{first.connection_uid or ''}",
                totals=sums,
                model=first.model,
                connection_uid=first.connection_uid,
            )
        if grouping is GroupBy.AGENT:
            return SummaryRow(
                key=first.agent_uid or first.agent_type or "",
                totals=sums,
                agent_uid=first.agent_uid,
                agent_type=first.agent_type,
            )
        return SummaryRow(key=first.day, totals=sums, day=first.day)

    async def _with_connection_names(self, rows: list[SummaryRow]) -> list[SummaryRow]:
        uids = sorted({r.connection_uid for r in rows if r.connection_uid})
        names = await self._names.names(uids) if uids else {}
        return [
            replace(r, connection_name=names.get(r.connection_uid)) if r.connection_uid else r
            for r in rows
        ]

    async def requests(
        self,
        *,
        filters: RequestFilters | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> Page[StoredUsage]:
        """Per-request rows newest first, paged by the shared opaque cursor
        (spec resource-framework "Page growing lists by an opaque cursor")."""
        narrowed = filters or RequestFilters()
        fingerprint = narrowed.fingerprint()
        position = decode_cursor(cursor, list_tag=_REQUESTS_LIST, filters=fingerprint)
        after = time_and_id(position, int)
        rows = await self._repo.requests(filters=narrowed, limit=limit + 1, after=after)
        return paginate(
            rows,
            limit,
            list_tag=_REQUESTS_LIST,
            filters=fingerprint,
            key=lambda r: position_of(r.record.started_at, r.id),
        )

    async def csv(
        self,
        range_name: str = "today",
        *,
        start: date | None = None,
        end: date | None = None,
        group_by: GroupBy | str = GroupBy.MODEL,
    ) -> str:
        """The summary as CSV: identity columns, every total, estimated cost."""
        summary = await self.summary(range_name, start=start, end=end, group_by=group_by)
        identity: dict[GroupBy, list[tuple[str, Callable[[SummaryRow], object]]]] = {
            GroupBy.MODEL: [
                ("model", lambda r: r.model),
                ("connection_uid", lambda r: r.connection_uid),
                ("connection", lambda r: r.connection_name),
            ],
            GroupBy.AGENT: [
                ("agent_uid", lambda r: r.agent_uid),
                ("agent_type", lambda r: r.agent_type),
            ],
            GroupBy.DAY: [("day", lambda r: r.day)],
        }
        columns = identity[summary.group_by]
        total_names = [f.name for f in fields(UsageTotals) if f.name != "cost_usd"]
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow([name for name, _ in columns] + total_names + ["estimated_cost_usd"])
        for row in summary.rows:
            writer.writerow(
                [_cell(get(row)) for _, get in columns]
                + [getattr(row.totals, n) for n in total_names]
                + [f"{row.totals.cost_usd:.6f}"]
            )
        return buf.getvalue()


def _cell(value: object) -> object:
    return "" if value is None else value


__all__ = ["GroupBy", "SummaryRow", "UsageQueryService", "UsageSummary", "UsageTotals"]
