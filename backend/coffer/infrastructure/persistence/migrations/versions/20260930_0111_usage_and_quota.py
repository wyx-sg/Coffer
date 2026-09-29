"""usage metering and subscription quota tables

ADR usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota:
the daemon ingests the model proxy's spooled usage records into
``usage_requests`` (one row per upstream attempt, deduplicated by ``source`` +
``dedupe_key``) and rolls them up per local day, agent, connection and model
into ``usage_daily`` in the same transaction. ``quota_snapshots`` keeps the
latest value of each subscription window an official feed reported.

The rollup's grouping columns are NOT NULL with ``''`` for "none": SQLite
treats NULLs in a UNIQUE constraint as distinct, so an upsert keyed on a NULL
would insert a second row instead of adding to the first.

Revision ID: 0111
Revises: 0110
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0111"
down_revision: str | None = "0110"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOKENS = (
    "input_tokens",
    "cache_write_5m_tokens",
    "cache_write_1h_tokens",
    "cache_read_tokens",
    "output_tokens",
    "reasoning_tokens",
    "web_search_requests",
)


def upgrade() -> None:
    op.create_table(
        "usage_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("attempt_id", sa.String(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("agent_uid", sa.String(), nullable=True),
        sa.Column("agent_type", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("request_class", sa.String(), nullable=True),
        sa.Column("connection_uid", sa.String(), nullable=True),
        sa.Column("member", sa.String(), nullable=True),
        sa.Column("wire", sa.String(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("stream", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("failed_over", sa.Boolean(), nullable=False),
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("usage_known", sa.Boolean(), nullable=False),
        *(sa.Column(name, sa.Integer(), nullable=True) for name in _TOKENS),
        sa.Column("speed", sa.String(), nullable=True),
        sa.Column("inference_geo", sa.String(), nullable=True),
        sa.Column("upstream_request_id", sa.String(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("price_version", sa.String(), nullable=True),
        sa.Column("unpriced", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("source", "dedupe_key", name="uq_usage_requests_source_dedupe"),
    )
    op.create_index("idx_usage_requests_started", "usage_requests", ["started_at"])

    op.create_table(
        "usage_daily",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("day", sa.String(), nullable=False),
        sa.Column("agent_uid", sa.String(), nullable=False),
        sa.Column("agent_type", sa.String(), nullable=False),
        sa.Column("connection_uid", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("unknown_requests", sa.Integer(), nullable=False),
        sa.Column("unpriced_requests", sa.Integer(), nullable=False),
        *(sa.Column(name, sa.Integer(), nullable=False) for name in _TOKENS),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.UniqueConstraint(
            "day",
            "agent_uid",
            "agent_type",
            "connection_uid",
            "model",
            name="uq_usage_daily_group",
        ),
    )

    op.create_table(
        "quota_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_type", sa.String(), nullable=False),
        sa.Column("window_key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("used_percent", sa.Float(), nullable=False),
        sa.Column("window_minutes", sa.Integer(), nullable=True),
        sa.Column("resets_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("plan", sa.String(), nullable=True),
        sa.UniqueConstraint("agent_type", "window_key", name="uq_quota_snapshots_window"),
    )


def downgrade() -> None:
    op.drop_table("quota_snapshots")
    op.drop_table("usage_daily")
    op.drop_index("idx_usage_requests_started", table_name="usage_requests")
    op.drop_table("usage_requests")
