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

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent (IF NOT EXISTS): a DB that was stamped at 0011 without the
    # table actually landing (a partial/interrupted migration) self-heals on
    # the next ``stamp 0010 && upgrade head`` instead of 500-ing forever.
    op.execute(
        "CREATE TABLE IF NOT EXISTS embedding_config ("
        "id INTEGER NOT NULL, "
        "enabled BOOLEAN NOT NULL DEFAULT 0, "
        "provider VARCHAR, "
        "model VARCHAR, "
        "base_url VARCHAR, "
        "credential_ref VARCHAR, "
        "dimensions INTEGER NOT NULL DEFAULT 768, "
        "updated_at TIMESTAMP NOT NULL, "
        "CONSTRAINT pk_embedding_config PRIMARY KEY (id), "
        "CONSTRAINT ck_embedding_config_singleton CHECK (id = 1)"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS embedding_config")
