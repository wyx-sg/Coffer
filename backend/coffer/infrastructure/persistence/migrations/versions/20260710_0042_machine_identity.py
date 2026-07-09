"""machine identity singleton (spec 010 amendment, ADR-043)

Revision ID: 0042
Revises: 0041
Create Date: 2026-07-10

Each installation mints a stable machine id (ULID) on first daemon start; a
human-friendly display name defaults to the hostname. Machine-local state about
the machine — never exported as vault data. The row is created lazily by the
identity service, not by this migration.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent (IF NOT EXISTS) so a partial/interrupted migration self-heals.
    op.execute(
        "CREATE TABLE IF NOT EXISTS machine_identity ("
        "id INTEGER NOT NULL, "
        "machine_id VARCHAR NOT NULL, "
        "display_name VARCHAR NOT NULL, "
        "created_at VARCHAR NOT NULL, "
        "updated_at VARCHAR NOT NULL, "
        "CONSTRAINT pk_machine_identity PRIMARY KEY (id), "
        "CONSTRAINT ck_machine_identity_singleton CHECK (id = 1), "
        "CONSTRAINT uq_machine_identity_machine_id UNIQUE (machine_id)"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS machine_identity")
