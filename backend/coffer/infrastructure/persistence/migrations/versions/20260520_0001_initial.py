"""initial

Revision ID: 0001
Revises:
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "name", name="uq_resources_kind_name"),
    )
    op.create_index(
        "idx_resources_kind_enabled",
        "resources",
        ["kind", "enabled"],
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("resource_kind", sa.String(), nullable=True),
        sa.Column("resource_name", sa.String(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_audit_resource",
        "audit_log",
        ["resource_kind", "resource_name", "timestamp"],
    )
    op.create_index("idx_audit_time", "audit_log", ["timestamp"])
    op.create_index("idx_audit_eventtype", "audit_log", ["event_type", "timestamp"])

    op.create_table(
        "retention_policies",
        sa.Column("table_name", sa.String(), primary_key=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("last_pruned_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "last_pruned_rows",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "retention_days IS NULL OR retention_days > 0",
            name="ck_retention_positive_or_null",
        ),
    )


def downgrade() -> None:
    op.drop_table("retention_policies")
    op.drop_index("idx_audit_eventtype", table_name="audit_log")
    op.drop_index("idx_audit_time", table_name="audit_log")
    op.drop_index("idx_audit_resource", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("idx_resources_kind_enabled", table_name="resources")
    op.drop_table("resources")
