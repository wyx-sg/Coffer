"""audit rows point at the resource's id, not at its name

Revision ID: 0067
Revises: 0066
Create Date: 2026-09-12

A rename used to rewrite history. ``audit_log`` identified a resource by
``(resource_kind, resource_name)``, so renaming ``acme`` to ``beta`` had to
bulk-update every row it had ever written — which left the log claiming that
the resource called ``beta`` was created, even though at creation time it was
called ``acme``. The repoint existed only because the mutable name was being
used as the key.

The id column fixes both halves: the trail follows the resource without being
touched, and each row keeps the label the resource carried when the event
happened. Backfill joins on the CURRENT name, so rows whose resource was since
renamed or deleted keep a NULL id and stay reachable by their label — which is
what the audit query's OR is for.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "0067"
down_revision: str | None = "0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    inspector = inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    if _has_column("audit_log", "resource_id"):
        return
    op.add_column("audit_log", sa.Column("resource_id", sa.Integer(), nullable=True))
    op.create_index("idx_audit_resource_id", "audit_log", ["resource_id", "timestamp"])
    # Point every row whose label still resolves at the row it describes.
    op.get_bind().execute(
        text(
            "UPDATE audit_log SET resource_id = ("
            "  SELECT r.id FROM resources r"
            "  WHERE r.kind = audit_log.resource_kind AND r.name = audit_log.resource_name"
            ") WHERE resource_kind IS NOT NULL AND resource_name IS NOT NULL"
        )
    )


def downgrade() -> None:
    if not _has_column("audit_log", "resource_id"):
        return
    op.drop_index("idx_audit_resource_id", table_name="audit_log")
    op.drop_column("audit_log", "resource_id")
