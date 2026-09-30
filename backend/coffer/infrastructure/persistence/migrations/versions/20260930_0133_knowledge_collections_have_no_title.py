"""knowledge collections carry no title

A collection is shown by its folder name, with the description its README
opens with (spec knowledge "Present a collection as one tree in the web UI",
spec resource-framework "Carry an optional editable title on the kinds that
have one"). The ``knowledge`` kind now declares ``titled=False``, so a title
is refused on register and on edit; this clears the ones already stored on
``knowledge`` rows. The column stays for the kinds that keep one. Nothing reads
it back for this kind, so there is no load-time shim.

The downgrade restores nothing: a cleared title is not recoverable, and an
older build reads an empty title as "show the name".

Revision ID: 0133
Revises: 0116
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0133"
down_revision: str | None = "0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if "resources" not in set(sa.inspect(bind).get_table_names()):
        return
    bind.execute(sa.text("UPDATE resources SET title = NULL WHERE kind = 'knowledge'"))


def downgrade() -> None:
    """Nothing to restore: cleared titles are gone, and an older build shows
    the name where a title is empty."""
