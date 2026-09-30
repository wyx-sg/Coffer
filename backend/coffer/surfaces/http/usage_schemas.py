"""Wire shapes of ``/api/v1/usage`` (ADR usage-is-metered-at-the-proxy-and-
subscriptions-show-only-official-quota)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from coffer.surfaces.http.handoff_schemas import HandoffOut


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


class QuotaWindowOut(BaseModel):
    key: str
    label: str
    #: ``None`` once the window has reset since it was observed.
    used_percent: float | None
    window_minutes: int | None
    resets_at: datetime | None
    #: When the source produced this value.
    as_of: datetime
    source: str
    stale: bool


class AgentQuotaOut(BaseModel):
    agent_type: str
    #: False when no official value has ever been observed — show no number.
    has_value: bool
    plan: str | None
    last_observed_at: datetime | None
    windows: list[QuotaWindowOut]
    #: Claude Code's row with no value: the prompt that hands opting in to the
    #: statusline wrapper to the person's agent
    #: (``application/usage/statusline_handoff.py``). ``None`` otherwise.
    handoff: HandoffOut | None = None


class QuotaListOut(BaseModel):
    agents: list[AgentQuotaOut]


class QuotaRefreshOut(BaseModel):
    refreshed: bool
    #: Why no read happened: ``too_soon``, ``codex_unavailable``,
    #: ``no_subscription``, ``read_failed``, ``no_windows``.
    reason: str | None
    agents: list[AgentQuotaOut]


class StatuslineQuotaIn(BaseModel):
    """The statusLine stdin JSON's ``rate_limits`` object, as Claude Code sent it."""

    rate_limits: dict[str, Any] = Field(default_factory=dict)


class StatuslineQuotaOut(BaseModel):
    accepted: bool


__all__ = [
    "AgentQuotaOut",
    "QuotaListOut",
    "QuotaRefreshOut",
    "QuotaWindowOut",
    "StatuslineQuotaIn",
    "StatuslineQuotaOut",
    "UsageRequestListOut",
    "UsageRequestOut",
    "UsageSummaryOut",
    "UsageSummaryRowOut",
    "UsageTotalsOut",
]
