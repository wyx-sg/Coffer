"""Wire shapes of ``/api/v1/usage`` (ADR usage-is-metered-at-the-proxy-and-
subscriptions-show-only-official-quota)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class UsageTotalsOut(BaseModel):
    requests: int
    #: Attempts whose stream ended before usage arrived: not in the token sums.
    unknown_usage_requests: int
    #: Attempts with known tokens but no price for the model: not in the cost.
    unpriced_requests: int
    input_tokens: int
    cache_write_5m_tokens: int
    cache_write_1h_tokens: int
    cache_read_tokens: int
    output_tokens: int
    #: A part of ``output_tokens``, not an addition to it.
    reasoning_tokens: int
    web_search_requests: int
    #: Estimated, from the price version stored with each request.
    estimated_cost_usd: float


class UsageSummaryRowOut(BaseModel):
    key: str
    model: str | None = None
    connection_uid: str | None = None
    #: The connection's current name (the provider), when it still exists.
    connection_name: str | None = None
    agent_uid: str | None = None
    agent_type: str | None = None
    day: str | None = None
    #: The agent types that sent the group's requests, most requests first.
    agent_types: list[str] = Field(default_factory=list)
    totals: UsageTotalsOut


class UsageSummaryOut(BaseModel):
    range: str
    #: Local days, both inclusive.
    start: date
    end: date
    group_by: str
    rows: list[UsageSummaryRowOut]
    totals: UsageTotalsOut
    cost_is_estimate: bool = True
    price_note: str


class UsageRequestOut(BaseModel):
    id: int
    source: str
    started_at: datetime
    agent_uid: str | None
    agent_type: str | None
    session_id: str | None
    request_class: str | None
    connection_uid: str | None
    member: str | None
    wire: str
    endpoint: str
    model: str | None
    stream: bool
    status: int | None
    outcome: str
    failed_over: bool
    ttft_ms: int | None
    duration_ms: int
    usage_known: bool
    input_tokens: int | None
    cache_write_5m_tokens: int | None
    cache_write_1h_tokens: int | None
    cache_read_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    web_search_requests: int | None
    estimated_cost_usd: float | None
    #: ``snapshot:<version>`` or ``override:<connection_uid>``.
    price_version: str | None
    unpriced: bool


class UsageRequestListOut(BaseModel):
    requests: list[UsageRequestOut]
    next_cursor: str | None


__all__ = [
    "UsageRequestListOut",
    "UsageRequestOut",
    "UsageSummaryOut",
    "UsageSummaryRowOut",
    "UsageTotalsOut",
]
