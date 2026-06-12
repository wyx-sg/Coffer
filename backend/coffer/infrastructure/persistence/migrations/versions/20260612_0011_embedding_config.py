"""global embedding configuration (redesign: embedding is no longer per-resource)

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-12

Embedding configuration moves OUT of each knowledge_base / memory store config
(JSON) into one installation-wide singleton row. The per-resource embedding
fields are simply ignored on load (pydantic drops unknown keys), so no data
migration of ``resources.config_json`` is required — vector retrieval stays off
until the operator configures the global embedding in Settings.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "embedding_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("base_url", sa.String(), nullable=True),
        sa.Column("credential_ref", sa.String(), nullable=True),
        sa.Column("dimensions", sa.Integer(), nullable=False, server_default=sa.text("768")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_embedding_config"),
        sa.CheckConstraint("id = 1", name="ck_embedding_config_singleton"),
    )


def downgrade() -> None:
    op.drop_table("embedding_config")
