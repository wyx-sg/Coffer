"""drop the sync rounds recorded as ``remote_too_old``

Replacing a remote at another layout removed the ``remote_too_old`` round
status: a remote at an older layout is now rebuilt in place, so that refusal
can no longer happen. Rounds already recorded with the status would no longer
parse, and the round history is advisory (nothing references a round row), so
they are deleted; the row's ``status`` column and its JSON payload carry the
same value, and the delete reads the column.

The downgrade has nothing to put back.

Revision ID: 0139
Revises: 0138
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0139"
down_revision: str | None = "0138"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "sync_runs" not in inspector.get_table_names():
        return
    op.execute(sa.text("DELETE FROM sync_runs WHERE status = 'remote_too_old'"))


def downgrade() -> None:
    pass
