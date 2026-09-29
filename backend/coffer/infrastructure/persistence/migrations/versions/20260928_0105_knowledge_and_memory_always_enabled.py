"""knowledge and memory lose their enabled switch: every row is set ``enabled = 1``

The ``knowledge`` and ``memory`` kinds now declare ``toggleable=False``: every
collection and every partition is served to every agent, and the kind-agnostic
enable/disable route refuses them. A row still stored disabled would be a state
no surface can show or change — the switch is gone from the pages — and one the
read paths no longer consult, so it is set back to enabled here rather than
left as a flag that says something nothing honours.

This WIDENS, and the argument is the one 0088 made for reach: the flag was
never a boundary. A disabled partition was still a folder of Markdown any agent
could open, and a disabled collection was still a directory under the root the
delivered skill tells an agent to grep. What it switched off was only what
Coffer itself pointed an agent at, and nobody used it for that — the whole
layer is already switched by its experimental feature.

Idempotent by the ``enabled = 0`` guard: a second run matches nothing. Scoped
by ``kind``, so no other kind's switch is read, let alone written.

Revision ID: 0105
Revises: 0104
Create Date: 2026-09-28
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0105"
down_revision: str | None = "0104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

_ALWAYS_ENABLED_KINDS = ("knowledge", "memory")


def upgrade() -> None:
    """Enable every ``knowledge`` and ``memory`` row stored disabled."""
    if "resources" not in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    result = op.get_bind().execute(
        sa.text("UPDATE resources SET enabled = 1 WHERE kind IN :kinds AND enabled = 0").bindparams(
            sa.bindparam("kinds", expanding=True)
        ),
        {"kinds": list(_ALWAYS_ENABLED_KINDS)},
    )
    logger.info("migration.0105.enabled; rows=%s", result.rowcount)


def downgrade() -> None:
    """One-way. Which rows were disabled is not recorded, and must not be guessed.

    A vault stepped below this revision reads every collection and partition as
    enabled, which is the state the code at that revision starts every new row
    in, and the switch is there again for anyone who wants to use it.
    """
