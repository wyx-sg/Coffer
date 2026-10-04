"""Read usage back: summaries from the daily rollup and the per-request list
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

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
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
from coffer.domain.usage.ranges import DateRange, RangeName, local_day, resolve_range

_REQUESTS_LIST = "usage_requests"


class GroupBy(StrEnum):
    MODEL = "model"
    PROVIDER = "provider"
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
    grouping: ``model`` + ``connection_*`` for model, ``connection_*`` for provider,
    ``agent_*`` for agent, ``day`` for day."""

    key: str
    totals: UsageTotals
    model: str | None = None
    connection_uid: str | None = None
    connection_name: str | None = None
    agent_uid: str | None = None
    agent_type: str | None = None
    day: str | None = None
    #: The agent types that sent the group's requests, most requests first —
    #: who used a model, or a day's top agent.
    agent_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class SummaryFilters:
    """Narrowing of a summary; ``None`` means any."""

    agent_type: str | None = None
    connection_uid: str | None = None

    def keeps(self, row: DailyUsage) -> bool:
        if self.agent_type is not None and row.agent_type != self.agent_type:
            return False
        return self.connection_uid is None or row.connection_uid == self.connection_uid


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


#: The most per-request rows a 24-hour summary reads.
_WINDOW_ROWS = 100_000


def _as_daily(stored: StoredUsage, tz: tzinfo) -> DailyUsage:
    """One request as the rollup row it would have contributed to."""
    rec = stored.record
    known = rec.usage_known

    def tokens(value: int | None) -> int:
        return (value or 0) if known else 0

    return DailyUsage(
        day=local_day(rec.started_at, tz),
        agent_uid=rec.agent_uid or None,
        agent_type=rec.agent_type or None,
        connection_uid=rec.connection_uid or None,
        model=rec.model or None,
        requests=1,
        unknown_requests=0 if known else 1,
        unpriced_requests=1 if stored.unpriced else 0,
        input_tokens=tokens(rec.input_tokens),
        cache_write_5m_tokens=tokens(rec.cache_write_5m_tokens),
        cache_write_1h_tokens=tokens(rec.cache_write_1h_tokens),
        cache_read_tokens=tokens(rec.cache_read_tokens),
        output_tokens=tokens(rec.output_tokens),
        reasoning_tokens=tokens(rec.reasoning_tokens),
        web_search_requests=tokens(rec.web_search_requests),
        cost_usd=stored.cost_usd or 0.0,
    )


def _group_key(group_by: GroupBy, row: DailyUsage) -> tuple[str | None, ...]:
    if group_by is GroupBy.MODEL:
        return (row.model, row.connection_uid)
    if group_by is GroupBy.PROVIDER:
        return (row.connection_uid,)
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
        filters: SummaryFilters | None = None,
    ) -> UsageSummary:
        span = self.resolve(range_name, start, end)
        grouping = GroupBy(group_by)
        narrowed = filters or SummaryFilters()
        if range_name == RangeName.LAST_24_HOURS:
            daily = [r for r in await self._last_24_hours() if narrowed.keeps(r)]
        else:
            daily = [
                r for r in await self._repo.daily(span.start_day, span.end_day) if narrowed.keeps(r)
            ]
        groups: dict[tuple[str | None, ...], tuple[DailyUsage, UsageTotals]] = {}
        senders: dict[tuple[str | None, ...], dict[str, int]] = {}
        total = UsageTotals()
        for row in daily:
            key = _group_key(grouping, row)
            first, sums = groups.get(key, (row, UsageTotals()))
            groups[key] = (first, sums.plus(row))
            if row.agent_type:
                by_type = senders.setdefault(key, {})
                by_type[row.agent_type] = by_type.get(row.agent_type, 0) + row.requests
            total = total.plus(row)
        if grouping is GroupBy.DAY:
            # Every day of the span, so a chart has no gaps: a quiet day is a 0.
            for day in _days(span):
                key = (day.isoformat(),)
                if key not in groups:
                    groups[key] = (DailyUsage(key[0], None, None, None, None), UsageTotals())
        rows = [
            replace(self._row(grouping, first, sums), agent_types=_most_first(senders.get(key)))
            for key, (first, sums) in groups.items()
        ]
        if grouping in (GroupBy.MODEL, GroupBy.PROVIDER):
            rows = await self._with_connection_names(rows)
        if grouping is GroupBy.DAY:
            rows.sort(key=lambda r: r.key)
        else:
            rows.sort(key=lambda r: (-r.totals.cost_usd, -r.totals.requests, r.key))
        return UsageSummary(range=span, group_by=grouping, rows=rows, totals=total)

    async def _last_24_hours(self) -> list[DailyUsage]:
        """The per-request rows of the 24 hours up to now, as rollup rows: a
        rolling window cuts through a local day, which ``usage_daily`` cannot."""
        now = self._clock.now()
        since = now - timedelta(hours=24)
        stored = await self._repo.requests(
            filters=RequestFilters(since=since), limit=_WINDOW_ROWS, after=None
        )
        return [_as_daily(s, self._tz) for s in stored]

    @staticmethod
    def _row(grouping: GroupBy, first: DailyUsage, sums: UsageTotals) -> SummaryRow:
        if grouping is GroupBy.MODEL:
            return SummaryRow(
                key=f"{first.model or ''}|{first.connection_uid or ''}",
                totals=sums,
                model=first.model,
                connection_uid=first.connection_uid,
            )
        if grouping is GroupBy.PROVIDER:
            return SummaryRow(
                key=first.connection_uid or "",
                totals=sums,
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


def _most_first(counts: dict[str, int] | None) -> tuple[str, ...]:
    if not counts:
        return ()
    return tuple(sorted(counts, key=lambda t: (-counts[t], t)))


__all__ = [
    "GroupBy",
    "SummaryFilters",
    "SummaryRow",
    "UsageQueryService",
    "UsageSummary",
    "UsageTotals",
]
