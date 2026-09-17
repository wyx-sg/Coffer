"""two lanes on disk, and the pass that fills one of them switched on

Revision ID: 0085
Revises: 0084
Create Date: 2026-09-17

Spec knowledge FR-042/FR-043/FR-044. A collection stops being a flat directory
of Markdown with two hidden folders beside it and becomes ``sources/`` +
``topics/``: what people contribute, and what Coffer's own model derives from
it. The rewrite itself is
``persistence/migrations/knowledge_tree_0085.py``, frozen alongside this file
so an old upgrade never changes behaviour because the live path helpers later
did, and it takes a backup of the whole knowledge root before it moves
anything (FR-043).

**Order.** The on-disk rewrite runs FIRST, before any DDL. It is the only step
that touches writing the user cannot get back, and running it first means a
failure anywhere in this revision leaves the database exactly as it was, with
the corpus's pre-migration copy sitting beside the root under a name that says
which upgrade made it.

**The renames.** ``auto_tidy_enabled`` / ``tidy_owner_machine_id`` /
``tidy_interval_s`` become ``auto_curate_enabled`` / ``curate_owner_machine_id``
/ ``curate_interval_s``. The pass they govern is not the one they were named
for: tidy rewrote the user's own files, curation may not touch them at all —
it reads ``sources/`` and writes only ``topics/``. SQLite cannot rename a
column in place, so the change goes through ``batch_alter_table``.

**The switch flips ON** (FR-032, FR-044). Tidy shipped off because an
unattended rewriter of a person's own writing is something they should switch
on deliberately. Curation is the opposite case: it is the *only* path from a
source to something an agent can read, so a vault where it never runs has an
empty ``topics/`` lane forever — the upgrade would take away the corpus and
give nothing back. The existing row is set on for the same reason, and
``curate_owner_machine_id`` is seeded with this machine, read from
``daemon-config.json`` beside the database the way 0079 read it. That seeding
does mean a migrated machine starts publishing the settings document to the
shared tree naming itself as owner; on a fleet, the second machine to be
upgraded conflicts on that document and the user picks. That is the intended
direction: a named owner that has to be resolved once beats two machines
curating one corpus into two different documents that git merges cleanly.

**The audit value.** ``knowledge_tidied`` rows are rewritten to
``knowledge_curated`` rather than deleted. Unlike the events 0077 and 0069
purged, this one still has a writer — the pass was renamed, not retired — so
the history stays readable under the name the code now uses. The value is
inlined rather than imported from ``AuditEventType``: a migration must mean the
same thing forever.

**The retired skill.** The shared ``coffer-knowledge`` skill Resource, its
agent bindings and its master folder all go (FR-042). The knowledge skill is
generated per agent now, with content that differs by which collections that
agent may see, and a registered shared master left behind would keep being
delivered beside the generated copy — the same layer described twice, one of
the descriptions wrong.

Every step is guarded: a database missing the column, the table or the row
still upgrades, and the rewrite is a no-op on a tree already in the new shape.
No compatibility shim is left anywhere — nothing reads the old column names or
the old document key after this (FR-042).
"""

from __future__ import annotations

import json
import logging
import pathlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from coffer.infrastructure.persistence.migrations.knowledge_tree_0085 import migrate

revision: str = "0085"
down_revision: str | None = "0084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

_CONFIG_TABLE = "internal_engine_config"

#: old name -> new name, in the order a reader of the settings page meets them.
_RENAMES = (
    ("auto_tidy_enabled", "auto_curate_enabled"),
    ("tidy_owner_machine_id", "curate_owner_machine_id"),
    ("tidy_interval_s", "curate_interval_s"),
)

#: The stored ``AuditEventType`` values, frozen at this revision.
_OLD_EVENT = "knowledge_tidied"
_NEW_EVENT = "knowledge_curated"

#: The shared skill this revision retires, by the name it was registered under.
_SHARED_SKILL = "coffer-knowledge"

#: Where the daemon caches this machine's derived id, and the store the shared
#: skill master lived in — both siblings of the database file.
_DAEMON_CONFIG = "daemon-config.json"
_MACHINE_ID_KEY = "machine_id"
_SKILLS_DIR = "skills"


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def _vault_dir() -> pathlib.Path | None:
    """The directory holding the database — ``~/.coffer`` on a real install.

    Derived rather than assumed: a test drives these migrations against a
    throwaway file under its own ``tmp_path``, and a hardcoded home would send
    this revision's writes into the developer's real vault. ``None`` for an
    in-memory database, which has no directory at all.
    """
    database = op.get_bind().engine.url.database
    if not database or database == ":memory:":
        return None
    return pathlib.Path(database).parent


def _this_machine_id() -> str | None:
    """The id cached beside this database, or ``None`` when unreadable.

    The same source and the same collapse-to-``None`` discipline as 0079: no
    file, no permission, not JSON, not an object, no id, a blank id, or a
    database with no directory. A migration must never fail because a cache is
    missing, and the honest answer to "which machine is this?" when nothing can
    say is to leave the owner NULL — which reads as "wherever this setting is
    read", the right answer for a vault that is not in a fleet.
    """
    directory = _vault_dir()
    if directory is None:
        return None
    try:
        payload = json.loads((directory / _DAEMON_CONFIG).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    cached = payload.get(_MACHINE_ID_KEY)
    if isinstance(cached, str) and cached.strip():
        return cached.strip()
    return None


def _skills_master_root() -> pathlib.Path | None:
    """``<vault>/skills`` — the store the shared skill master lived in."""
    directory = _vault_dir()
    return None if directory is None else directory / _SKILLS_DIR


def _rename_columns(
    pairs: Sequence[tuple[str, str]], *, enabled_default: sa.sql.ColumnElement[bool]
) -> None:
    """Rename whichever of ``pairs`` is actually present, in one table rebuild.

    SQLite has no in-place column rename, so ``batch_alter_table`` recreates
    the table; doing all three in one batch means one rebuild rather than
    three. A pair whose old column is gone (or whose new one already exists) is
    skipped, so a database that has been through part of this still upgrades.
    """
    todo = [
        (old, new)
        for old, new in pairs
        if _has_column(_CONFIG_TABLE, old) and not _has_column(_CONFIG_TABLE, new)
    ]
    if not todo:
        return
    with op.batch_alter_table(_CONFIG_TABLE) as batch:
        for old, new in todo:
            if old.startswith("auto_"):
                # The switch also changes what a fresh row gets (FR-032).
                batch.alter_column(
                    old,
                    new_column_name=new,
                    existing_type=sa.Boolean(),
                    existing_nullable=False,
                    server_default=enabled_default,
                )
            else:
                batch.alter_column(old, new_column_name=new)


def _seed_curation() -> None:
    """Switch curation on for the row that exists, and name this machine.

    FR-044. An existing vault has a row holding tidy's shipped-off default, and
    leaving it there would migrate a user into a corpus whose readable lane is
    empty and stays that way. The owner is only written when it is currently
    NULL: a user who already chose a machine chose it for the same corpus, and
    this upgrade is not the moment to overrule them.
    """
    if not _has_column(_CONFIG_TABLE, "auto_curate_enabled"):
        return
    bind = op.get_bind()
    bind.execute(sa.text(f"UPDATE {_CONFIG_TABLE} SET auto_curate_enabled = 1"))
    machine_id = _this_machine_id()
    if machine_id is None or not _has_column(_CONFIG_TABLE, "curate_owner_machine_id"):
        logger.info("0085: curation owner left unset (no machine id cached beside the database)")
        return
    bind.execute(
        sa.text(
            f"UPDATE {_CONFIG_TABLE} SET curate_owner_machine_id = :machine "
            "WHERE curate_owner_machine_id IS NULL"
        ),
        {"machine": machine_id},
    )


def _rewrite_audit(old: str, new: str) -> None:
    """Carry the pass's history over to its new name."""
    if not _has_table("audit_log"):
        return
    op.get_bind().execute(
        sa.text("UPDATE audit_log SET event_type = :new WHERE event_type = :old"),
        {"new": new, "old": old},
    )


def _drop_shared_skill_rows() -> None:
    """Delete the shared ``coffer-knowledge`` Resource and its bindings.

    The bindings go first and explicitly rather than by cascade: the join table
    declares ``ON DELETE CASCADE``, but SQLite enforces foreign keys only when
    ``PRAGMA foreign_keys`` is on, which is not something a migration should
    assume about the connection it was handed.
    """
    if not _has_table("resources"):
        return
    bind = op.get_bind()
    ids = [
        row[0]
        for row in bind.execute(
            sa.text("SELECT id FROM resources WHERE kind = 'skill' AND name = :name"),
            {"name": _SHARED_SKILL},
        ).fetchall()
    ]
    if not ids:
        return
    if _has_table("skill_agent_bindings"):
        bind.execute(
            sa.text("DELETE FROM skill_agent_bindings WHERE skill_resource_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": ids},
        )
    bind.execute(
        sa.text("DELETE FROM resources WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": ids},
    )


def upgrade() -> None:
    # 1. The user's files, backed up first. Before every drop and rename below,
    #    so a failure further down costs nothing that is not recoverable.
    report = migrate(master_root=_skills_master_root())
    logger.info("knowledge tree split into lanes: %s", report)

    # 2. The settings the curation pass is steered by.
    _rename_columns(_RENAMES, enabled_default=sa.true())
    _seed_curation()

    # 3. The history of the pass, under the name the code now uses.
    _rewrite_audit(_OLD_EVENT, _NEW_EVENT)

    # 4. The delivery this revision replaces.
    _drop_shared_skill_rows()


def downgrade() -> None:
    """Put the column names back, and nothing else.

    The names have to come back: the revisions below this one drop
    ``tidy_interval_s`` (0082), ``tidy_owner_machine_id`` (0074) and
    ``auto_tidy_enabled`` (0066) by name, and would fail on a column that is no
    longer called that. The switch goes back to shipping off with them, because
    down there it governs tidy again.

    What does not come back is the tree, the shared skill's Resource row, or
    its master folder. That is deliberate (FR-042): this is a one-way
    migration, the corpus's pre-migration copy is the backup beside the root,
    and re-registering a skill whose bytes are gone would deliver an agent a
    dangling link. The audit rows are renamed back so a build below this
    revision reads its own history under its own name.
    """
    _rename_columns(
        tuple((new, old) for old, new in _RENAMES),
        enabled_default=sa.false(),
    )
    _rewrite_audit(_NEW_EVENT, _OLD_EVENT)
