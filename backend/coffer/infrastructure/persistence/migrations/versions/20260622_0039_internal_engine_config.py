"""internal-engine model selection (spec 011 amendment 2026-06-22b)

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-22

Coffer's internal LLM engine (organizer / reorg / distill / coffer__ask) takes
its endpoint + key from the ``internal_default`` connection, but its MODEL is now
chosen separately — the connection no longer owns a model. One installation-wide
singleton row holds the model id; ``NULL`` until the operator picks one.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent (IF NOT EXISTS) so a partial/interrupted migration self-heals.
    op.execute(
        "CREATE TABLE IF NOT EXISTS internal_engine_config ("
        "id INTEGER NOT NULL, "
        "model VARCHAR, "
        "updated_at TIMESTAMP NOT NULL, "
        "CONSTRAINT pk_internal_engine_config PRIMARY KEY (id), "
        "CONSTRAINT ck_internal_engine_config_singleton CHECK (id = 1)"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS internal_engine_config")
