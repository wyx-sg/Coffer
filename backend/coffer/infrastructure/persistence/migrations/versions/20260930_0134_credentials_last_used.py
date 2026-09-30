"""When each stored secret was last used on this machine.

The Secrets page lists each secret with when it was last used (spec secret
"List every stored and cited secret with what uses it"). The store stamps
``last_used_at`` when it decrypts a value for a consumer; the column is
machine-local — sync carries only ref and ciphertext — and nullable, because a
secret stored before this revision has never been seen in use.

Nothing to back-fill: no earlier record says when a value was used.

Revision ID: 0134
Revises: 0115
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0134"
down_revision: str | None = "0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("credentials") as batch:
        batch.add_column(sa.Column("last_used_at", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("credentials") as batch:
        batch.drop_column("last_used_at")
