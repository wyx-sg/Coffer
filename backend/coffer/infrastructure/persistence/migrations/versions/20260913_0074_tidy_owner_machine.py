"""Name the one machine allowed to run the unattended tidy pass.

Spec vault-sync "Run an unattended rewriter on one owner machine". The knowledge tidy pass merges
duplicate notes, splits overgrown ones and deletes the file whose content now
lives elsewhere. On one machine that is housekeeping; on several it is a
failure git cannot see — each machine merges the same two notes into a
*different* topic document, both agree the sources are deleted, and the two
topics are additions at different paths, so the merge is clean and the vault
quietly holds the same knowledge twice.

``NULL`` means "wherever this setting is read", which is the right answer for a
single-machine vault and is what every existing row gets: enabling tidy before
there was a fleet cannot retroactively become a choice the user never made.

Revision ID: 0074
Revises: 0073
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0074"
down_revision: str | None = "0073"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "internal_engine_config",
        sa.Column("tidy_owner_machine_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("internal_engine_config", "tidy_owner_machine_id")
