"""rebuild the memory layer around Coffer's own notes

The memory layer stops storing the agents' words and starts storing its own
(spec memory "Write notes in Coffer's own words", and the ADR
`aggregate-agent-memory-never-write-it`). Three things in the database have to
move with it, and one thing on disk.

**The partitions go, and are rebuilt.** A partition used to be keyed on the
working directory an entry was learned in; it is now keyed on the
**repository** (see "Identify a partition by its repository"), so its
``config`` changes shape — ``project_root`` becomes ``repository_key`` plus
``repository_path`` — and its *membership* changes with it: a worktree and its
main checkout now collapse into one partition, and a directory inside no
repository gets none at all (see "Create no partition for a non-repository
directory"). On the machine this was measured against, that is six of sixteen
partitions disappearing and several others merging.

Rewriting each row in place would mean guessing, from a path that may no longer
exist, which repository it belonged to. The rows are **derived** ("Keep the
memory tree derived and local" covers the Resource row explicitly, not only the
files), so this migration deletes them instead and lets the next aggregation
pass recreate them from the agents' own memory, which is the only authority on
the subject. The cost is a scope a developer had narrowed by hand, which
returns to its default of "the agents it was aggregated from"; the alternative
is a half-migrated row naming a repository nobody verified.

**The tree goes with them**, for the same reason and with the same authority:
``facts/``, ``summary.md`` and ``README.md`` are a layout no code reads any
more, and leaving them beside the new ``notes/`` / ``MEMORY.md`` / ``.raw/``
would leave a partition looking like it holds twice what it holds. The next
aggregation rebuilds it. ``$COFFER_MEMORY_ROOT`` is honoured, so a test run
never reaches a developer's real vault.

**The upkeep switch is renamed.** ``organise`` is not what the pass is called
any more, and a column named for a pass that no longer exists is the drift
this repository's contract gates exist to catch.

**The audit history is rewritten, not dropped.** ``memory_organised`` rows
record passes that really happened; they are relabelled ``memory_distilled``
so the audit surface can still render them rather than falling back to a raw
event code.

One-way, with no compatibility shim left behind.

Revision ID: 0086
Revises: 0085
Create Date: 2026-09-17
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0086"
down_revision: str | None = "0085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

_ENGINE_TABLE = "internal_engine_config"
_RENAMES = (
    ("auto_organise_enabled", "auto_distil_enabled"),
    ("organise_interval_s", "distil_interval_s"),
)


def _memory_root() -> pathlib.Path:
    """The memory root, resolved the way ``infrastructure/memory/paths`` does.

    Duplicated rather than imported: a migration must keep working when the
    module it would import has moved on, and this is two lines of environment
    lookup. The override is honoured for the reason it exists — a test run
    must never delete a developer's real ``~/.coffer/memory``.
    """
    override = os.environ.get("COFFER_MEMORY_ROOT")
    if override:
        return pathlib.Path(override)
    home = pathlib.Path(os.environ.get("HOME", "~")).expanduser()
    return home / ".coffer" / "memory"


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()

    if _ENGINE_TABLE in tables:
        present = _columns(_ENGINE_TABLE)
        pending = [(old, new) for old, new in _RENAMES if old in present and new not in present]
        if pending:
            # SQLite cannot rename a column in place before 3.25 and the
            # project's own convention is batch mode regardless, so the table
            # is rebuilt with the new names and every value carried across.
            with op.batch_alter_table(_ENGINE_TABLE) as batch:
                for old, new in pending:
                    batch.alter_column(old, new_column_name=new)

    bind = op.get_bind()

    if "resources" in tables:
        # Derived rows (see "Keep the memory tree derived and local").
        # Aggregation recreates them keyed on the repository, which is the only
        # thing that can decide which of them were ever really distinct.
        deleted = bind.execute(
            sa.text("DELETE FROM resources WHERE kind = :kind"), {"kind": "memory"}
        ).rowcount
        logger.info("migration.0086.memory_partitions_dropped; count=%s", deleted)

    if "audit_log" in tables:
        bind.execute(
            sa.text("UPDATE audit_log SET event_type = :new WHERE event_type = :old"),
            {"new": "memory_distilled", "old": "memory_organised"},
        )

    root = _memory_root()
    if root.is_dir():
        for partition in sorted(root.iterdir()):
            if not partition.is_dir():
                continue
            # Only an old-layout partition is removed. A directory already
            # holding `notes/` was written by the new code — this migration
            # running twice, or a partition created between the two — and
            # deleting it would throw away a distillation that cost a model
            # call to produce.
            if (partition / "notes").is_dir():
                continue
            shutil.rmtree(partition, ignore_errors=True)
            logger.info("migration.0086.memory_partition_removed; name=%s", partition.name)
        # The skip cache is keyed by native path, not by layout, but a rebuild
        # has to actually re-read every source to repopulate `.raw/` — and a
        # digest match alone must never suppress that.
        state = root / ".source_state.json"
        if state.is_file():
            state.unlink()


def downgrade() -> None:
    """Rename the columns back. The deletions are not reversible.

    The partitions and the tree were derived and are gone; a downgrade leaves
    the next aggregation to rebuild whichever layout the code at that revision
    writes, which is exactly what it would have done anyway.
    """
    if _ENGINE_TABLE not in _tables():
        return
    present = _columns(_ENGINE_TABLE)
    pending = [(new, old) for old, new in _RENAMES if new in present and old not in present]
    if not pending:
        return
    with op.batch_alter_table(_ENGINE_TABLE) as batch:
        for new, old in pending:
            batch.alter_column(new, new_column_name=old)
