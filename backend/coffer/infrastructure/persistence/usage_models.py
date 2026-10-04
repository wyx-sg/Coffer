"""ORM models for usage metering (ADR
usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

Two tables:

* ``usage_requests`` — one row per upstream attempt the proxy spooled: every
  :class:`~coffer.domain.usage.records.UsageRecord` field plus the cost computed
  at ingest and the price version that produced it. ``UNIQUE(source,
  dedupe_key)`` is what makes a repeated ingest write nothing twice. Pruned on
  the MCP-calls retention window.
* ``usage_daily`` — the rollup the Usage page reads: one row per local day,
  agent, connection and model. Upserted in the same transaction as the detail
  insert, and only when that insert added a row. The grouping columns store
  ``''`` for "none" rather than NULL, because SQLite treats NULLs in a UNIQUE
  constraint as distinct and an upsert would never find the row. Kept 365 days.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class UsageRequestModel(Base):
    __tablename__ = "usage_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String, nullable=False)
    attempt_id: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    agent_uid: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_type: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    request_class: Mapped[str | None] = mapped_column(String, nullable=True)
    connection_uid: Mapped[str | None] = mapped_column(String, nullable=True)
    member: Mapped[str | None] = mapped_column(String, nullable=True)
    wire: Mapped[str] = mapped_column(String, nullable=False)
    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    stream: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    failed_over: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_known: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_write_5m_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_write_1h_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    web_search_requests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speed: Mapped[str | None] = mapped_column(String, nullable=True)
    inference_geo: Mapped[str | None] = mapped_column(String, nullable=True)
    upstream_request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    #: Estimated at ingest; NULL when usage is unknown or the model unpriced.
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: ``snapshot:<version>`` or ``override:<connection_uid>``.
    price_version: Mapped[str | None] = mapped_column(String, nullable=True)
    #: Usage was known but no price covered the model.
    unpriced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("source", "dedupe_key", name="uq_usage_requests_source_dedupe"),
        Index("idx_usage_requests_started", "started_at"),
    )


class UsageDailyModel(Base):
    __tablename__ = "usage_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: The LOCAL day (``YYYY-MM-DD``) the attempts started on.
    day: Mapped[str] = mapped_column(String, nullable=False)
    agent_uid: Mapped[str] = mapped_column(String, nullable=False, default="")
    agent_type: Mapped[str] = mapped_column(String, nullable=False, default="")
    connection_uid: Mapped[str] = mapped_column(String, nullable=False, default="")
    model: Mapped[str] = mapped_column(String, nullable=False, default="")
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unpriced_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_write_5m_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_write_1h_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    web_search_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    __table_args__ = (
        UniqueConstraint(
            "day",
            "agent_uid",
            "agent_type",
            "connection_uid",
            "model",
            name="uq_usage_daily_group",
        ),
    )


__all__ = ["UsageDailyModel", "UsageRequestModel"]
