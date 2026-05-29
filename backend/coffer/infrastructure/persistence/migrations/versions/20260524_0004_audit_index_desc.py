"""audit + invocation timestamp indexes — DESC ordering

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-24

CODE-007: Audit/invocation list queries are always ``ORDER BY timestamp DESC``
with a small ``LIMIT``. Plain ascending indexes force SQLite to scan in the
"wrong" direction; explicit DESC indexes let the planner walk the tail of
the b-tree directly.

We DROP + CREATE the affected indexes here rather than mutating the
already-shipped migrations 0001 / 0002 (those are immutable history).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # audit_log: replace the three timestamp-ordered indexes with DESC variants.
    op.drop_index("idx_audit_resource", table_name="audit_log")
    op.drop_index("idx_audit_time", table_name="audit_log")
    op.drop_index("idx_audit_eventtype", table_name="audit_log")
    op.create_index(
        "idx_audit_resource",
        "audit_log",
        ["resource_kind", "resource_name", text("timestamp DESC")],
    )
    op.create_index("idx_audit_time", "audit_log", [text("timestamp DESC")])
    op.create_index(
        "idx_audit_eventtype",
        "audit_log",
        ["event_type", text("timestamp DESC")],
    )

    # mcp_invocations: same treatment for the three timestamp-ordered indexes.
    op.drop_index("idx_invocations_resource", table_name="mcp_invocations")
    op.drop_index("idx_invocations_time", table_name="mcp_invocations")
    op.drop_index("idx_invocations_session", table_name="mcp_invocations")
    op.create_index(
        "idx_invocations_resource",
        "mcp_invocations",
        ["resource_name", text("timestamp DESC")],
    )
    op.create_index(
        "idx_invocations_time",
        "mcp_invocations",
        [text("timestamp DESC")],
    )
    op.create_index(
        "idx_invocations_session",
        "mcp_invocations",
        ["session_id", text("timestamp DESC")],
    )


def downgrade() -> None:
    # Revert to the ascending-timestamp indexes shipped in 0001 / 0002.
    op.drop_index("idx_invocations_session", table_name="mcp_invocations")
    op.drop_index("idx_invocations_time", table_name="mcp_invocations")
    op.drop_index("idx_invocations_resource", table_name="mcp_invocations")
    op.create_index(
        "idx_invocations_session",
        "mcp_invocations",
        ["session_id", "timestamp"],
    )
    op.create_index("idx_invocations_time", "mcp_invocations", ["timestamp"])
    op.create_index(
        "idx_invocations_resource",
        "mcp_invocations",
        ["resource_name", "timestamp"],
    )

    op.drop_index("idx_audit_eventtype", table_name="audit_log")
    op.drop_index("idx_audit_time", table_name="audit_log")
    op.drop_index("idx_audit_resource", table_name="audit_log")
    op.create_index(
        "idx_audit_eventtype",
        "audit_log",
        ["event_type", "timestamp"],
    )
    op.create_index("idx_audit_time", "audit_log", ["timestamp"])
    op.create_index(
        "idx_audit_resource",
        "audit_log",
        ["resource_kind", "resource_name", "timestamp"],
    )
