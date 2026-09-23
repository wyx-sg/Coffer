"""Knowledge: the two lanes become one co-edited tree (spec knowledge FR-042).

The on-disk half is ``persistence/migrations/knowledge_tree_0101.py``, frozen
alongside this file: every collection's ``sources/`` and ``topics/`` are backed
up, their Markdown is queued in the collection's hidden inbox for the curation
sweep to distil again into one tree of documents, and both lanes are removed.

Nothing in the database changes. The curation settings 0085 seeded — on, owned
by the machine that migrated — are the ones the sweep that drains the inbox
reads, and a knowledge collection is still one ``resources`` row.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from coffer.infrastructure.persistence.migrations.knowledge_tree_0101 import migrate

revision: str = "0101"
down_revision: str | None = "0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    report = migrate()
    logger.info("knowledge lanes queued for one tree: %s", report)


def downgrade() -> None:
    """Nothing to reverse in the database.

    The tree is not put back: the lanes' files were queued for re-curation and
    may already have been merged into documents, and the originals were
    dropped. The backup this revision took is the way back, by hand.
    """
