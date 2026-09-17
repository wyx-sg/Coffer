"""knowledge and memory withdraw from per-agent reach: their ``scope_json`` goes NULL

The ``knowledge`` and ``memory`` kinds stop declaring ``supports_scope``, so
the column that held their reach has to be emptied as well — a row left
carrying a scope no code reads any more is a permission the page would keep
showing and nothing would honour.

This migration WIDENS, deliberately. Everywhere else in this tree that is the
one direction a script over someone's live vault must not take (0076 spends its
whole body avoiding it), so the exception has to be argued rather than
asserted, and the two kinds argue it differently.

**``knowledge`` never used the knob.** Every ``kind='knowledge'`` row in the
vault this was measured against carried ``scope_json IS NULL`` — unrestricted,
the default, never once narrowed in the weeks the field existed. There is no
restriction here to preserve because nobody ever drew one.

**``memory`` used it without being asked.** Every ``kind='memory'`` row carried
a value, and not one of them was chosen by a person: the aggregation pass wrote
each partition's scope automatically, to "the agents this partition was
aggregated from". An auto-default is not a decision, and this one worked
against the layer it was defending. ``memory/coffer`` was scoped to
``["claude-code"]``, so a Codex session in the Coffer repository was served no
project memory at all; the ``account*`` partitions were scoped to ``["codex"]``,
so Claude Code was served none of theirs. A layer whose entire purpose is to
let several agents read what the others learned was defaulting to hiding it,
and the default was invisible — nobody set it, so nobody thought to look at it.

Widening is safe here for a reason that holds for both kinds and for neither of
the four that keep their scope: this reach was never a boundary. Both kinds
serve files on disk to an agent that is handed the path, and knowledge's own
delivered skill tells the agent to grep the whole root. Reach could prevent a
mistaken retrieval; it could not prevent a deliberate read, and it was never
the thing standing between an agent and the bytes. ``mcp_server``, ``skill``,
``provider`` and ``channel`` are untouched — for them reach decides what is
exposed, delivered, written into a config file, or allowed to drive an agent,
and those are real answers this migration must not disturb.

Idempotent by the ``IS NOT NULL`` guard: a second run matches nothing. Scoped
by ``kind``, so no other kind's row is read, let alone written.

Revision ID: 0088
Revises: 0087
Create Date: 2026-09-18
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0088"
down_revision: str | None = "0087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

_WITHDRAWN_KINDS = ("knowledge", "memory")


def upgrade() -> None:
    """Clear the reach of every ``knowledge`` and ``memory`` row."""
    if "resources" not in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    result = op.get_bind().execute(
        sa.text(
            "UPDATE resources SET scope_json = NULL WHERE kind IN :kinds AND scope_json IS NOT NULL"
        ).bindparams(sa.bindparam("kinds", expanding=True)),
        {"kinds": list(_WITHDRAWN_KINDS)},
    )
    logger.info("migration.0088.reach_cleared; rows=%s", result.rowcount)


def downgrade() -> None:
    """One-way. The cleared values cannot be recovered, and must not be invented.

    ``knowledge`` had nothing to restore — every row was already ``NULL``. For
    ``memory`` the values are gone, and the only thing a downgrade could put
    back is a fresh guess at "the agents this partition was aggregated from",
    computed from a vault that has since moved on. That would be a NEW
    restriction wearing an old one's clothes: narrower than what the vault has
    now, chosen by this script rather than by the user, and — since it is the
    very default this revision withdrew for doing harm — likely to hide
    partitions from the agents that can currently read them.

    So nothing is written. A vault stepped below this revision reads ``NULL``
    as unrestricted, which is what every ``knowledge`` row said all along and
    what every ``memory`` row should have said, and the code at that revision
    is free to set its own scope again if it wants one.
    """
