"""/api/v1/usage — metered API-key usage (ADR
usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

* ``GET /summary`` — the daily rollup summed over a range, grouped by model,
  agent or day, optionally narrowed to one agent type and one connection.
  Costs are estimates and say so.
* ``GET /requests`` — the per-request detail, newest first, paged by the
  shared opaque cursor (spec resource-framework "Page growing lists by an
  opaque cursor").
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from coffer.application.usage.ports import RequestFilters, StoredUsage
from coffer.application.usage.query import (
    GroupBy,
    SummaryFilters,
    SummaryRow,
    UsageQueryService,
    UsageTotals,
)
from coffer.domain.usage.ranges import InvalidRange
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.usage_dependencies import get_usage_query_service
from coffer.surfaces.http.usage_schemas import (
    UsageRequestListOut,
    UsageRequestOut,
    UsageSummaryOut,
    UsageSummaryRowOut,
    UsageTotalsOut,
)

router = APIRouter(
    prefix="/api/v1/usage",
    tags=["usage"],
    dependencies=[Depends(require_token)],
)

_RANGE = Query(
    default="today", alias="range", description="today | 24h | 7d | 30d | month | custom"
)
_FROM = Query(default=None, alias="from", description="First local day (custom range)")
_TO = Query(default=None, alias="to", description="Last local day, inclusive (custom range)")
_GROUP = Query(default=GroupBy.MODEL, description="model | agent | day")
_AGENT = Query(default=None, description="Only requests this agent type sent")
_CONNECTION = Query(default=None, description="Only requests this connection served")


def _bad_range(exc: InvalidRange) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _totals(t: UsageTotals) -> UsageTotalsOut:
    return UsageTotalsOut(
        requests=t.requests,
        unknown_usage_requests=t.unknown_usage_requests,
        unpriced_requests=t.unpriced_requests,
        input_tokens=t.input_tokens,
        cache_write_5m_tokens=t.cache_write_5m_tokens,
        cache_write_1h_tokens=t.cache_write_1h_tokens,
        cache_read_tokens=t.cache_read_tokens,
        output_tokens=t.output_tokens,
        reasoning_tokens=t.reasoning_tokens,
        web_search_requests=t.web_search_requests,
        estimated_cost_usd=round(t.cost_usd, 6),
    )


def _row(r: SummaryRow) -> UsageSummaryRowOut:
    return UsageSummaryRowOut(
        key=r.key,
        model=r.model,
        connection_uid=r.connection_uid,
        connection_name=r.connection_name,
        agent_uid=r.agent_uid,
        agent_type=r.agent_type,
        day=r.day,
        agent_types=list(r.agent_types),
        totals=_totals(r.totals),
    )


def _request(s: StoredUsage) -> UsageRequestOut:
    rec = s.record
    return UsageRequestOut(
        id=s.id,
        source=rec.source,
        started_at=rec.started_at,
        agent_uid=rec.agent_uid,
        agent_type=rec.agent_type,
        session_id=rec.session_id,
        request_class=rec.request_class,
        connection_uid=rec.connection_uid,
        member=rec.member,
        wire=str(rec.wire),
        endpoint=rec.endpoint,
        model=rec.model,
        stream=rec.stream,
        status=rec.status,
        outcome=str(rec.outcome),
        ttft_ms=rec.ttft_ms,
        duration_ms=rec.duration_ms,
        usage_known=rec.usage_known,
        input_tokens=rec.input_tokens,
        cache_write_5m_tokens=rec.cache_write_5m_tokens,
        cache_write_1h_tokens=rec.cache_write_1h_tokens,
        cache_read_tokens=rec.cache_read_tokens,
        output_tokens=rec.output_tokens,
        reasoning_tokens=rec.reasoning_tokens,
        web_search_requests=rec.web_search_requests,
        estimated_cost_usd=s.cost_usd,
        price_version=s.price_version,
        unpriced=s.unpriced,
    )


@router.get("/summary", response_model=UsageSummaryOut)
async def usage_summary(
    range_name: str = _RANGE,
    start: date | None = _FROM,
    end: date | None = _TO,
    group_by: GroupBy = _GROUP,
    agent_type: str | None = _AGENT,
    connection_uid: str | None = _CONNECTION,
    svc: UsageQueryService = Depends(get_usage_query_service),  # noqa: B008
) -> UsageSummaryOut:
    filters = SummaryFilters(agent_type=agent_type, connection_uid=connection_uid)
    try:
        summary = await svc.summary(
            range_name, start=start, end=end, group_by=group_by, filters=filters
        )
    except InvalidRange as exc:
        raise _bad_range(exc) from exc
    return UsageSummaryOut(
        range=range_name,
        start=summary.range.start,
        end=summary.range.end,
        group_by=summary.group_by.value,
        rows=[_row(r) for r in summary.rows],
        totals=_totals(summary.totals),
        cost_is_estimate=summary.cost_is_estimate,
        price_note=summary.price_note,
    )


@router.get("/requests", response_model=UsageRequestListOut)
async def usage_requests(
    limit: int = Query(default=50, ge=1, le=500),
    cursor: str | None = Query(
        default=None,
        description="The previous page's next_cursor; bound to the filters it was issued with.",
    ),
    agent_uid: str | None = Query(default=None),
    connection_uid: str | None = Query(default=None),
    model: str | None = Query(default=None),
    svc: UsageQueryService = Depends(get_usage_query_service),  # noqa: B008
) -> UsageRequestListOut:
    filters = RequestFilters(agent_uid=agent_uid, connection_uid=connection_uid, model=model)
    page = await svc.requests(filters=filters, limit=limit, cursor=cursor)
    return UsageRequestListOut(
        requests=[_request(s) for s in page.items], next_cursor=page.next_cursor
    )
