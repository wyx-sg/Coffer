"""credentials table for the encrypted credential store

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-12

Secrets move from the OS keychain into this table as Fernet ciphertext
(envelope encryption; master key in ~/.coffer/master.key or the keychain).
Existing keychain entries are migrated at daemon startup, not here — Alembic
must not touch the OS keychain.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("ref", sa.String(), primary_key=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("credentials")
