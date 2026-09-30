"""Where the previous layout kept each tree, where the new one keeps it, and
the names of the upgrade's own files (plan q9 §3).

Every path is relative to ``~/.coffer`` so a rehearsal in a throwaway home,
or a test's fake one, moves every one of them. Only the upgrade reads the old
locations: nothing else in this build knows them (no load-time shim).
"""

from __future__ import annotations

from pathlib import Path

from coffer.infrastructure.vault.home import coffer_home

#: The trees the previous layout kept at the top of ``~/.coffer``, and where
#: this layout keeps them — in move order. ``skills/coffer-guide`` goes first,
#: out of ``skills/``, because it is Coffer's own rendered skill (derived), not
#: a person's (vault).
TREE_MOVES: tuple[tuple[str, str], ...] = (
    ("skills/coffer-guide", "derived/skills/coffer-guide"),
    ("knowledge", "vault/knowledge"),
    ("skills", "vault/skills"),
    ("memory", "derived/memory"),
    ("chat-media", "content/chat-media"),
    ("channel-media", "content/channel-media"),
    ("workspace", "content/workspace"),
    ("cache/agent", "derived/cache/agent"),
)

#: Trees the previous layout already kept where this one does.
IN_PLACE: tuple[str, ...] = ("vault/memory-triggers",)

#: The class directories the upgrade creates; a rollback moves aside each one
#: the home did not already have.
CLASS_DIRS: tuple[str, ...] = ("vault", "local", "content", "derived")

#: The last Alembic revision whose tables still hold the pre-vault state: the
#: upgrade reads the old database there, and the next revision drops them.
PRE_LAYOUT_REVISION = "0116"
LAYOUT_REVISION = "0136"

LEGACY_DB = "coffer.db"
RUNS_DB = "runs.db"
SIDE_FILES: tuple[str, ...] = ("-wal", "-shm")
#: The database as it was before the upgrade touched it; never opened for
#: writing again (ADR every-vault-file-carries-its-format-version).
DB_BACKUP = "coffer.db.pre-vault"
#: The rest of the backup set: the old knowledge history, the knowledge
#: documents as they were before their curation stamps were stripped, and
#: ``daemon-config.json`` (revision 0116 rewrites it).
BACKUP_DIR = "pre-vault"
KNOWLEDGE_GIT_BACKUP = "pre-vault/knowledge.git"
STAMPED_BACKUP = "pre-vault/knowledge-stamped"
DAEMON_CONFIG = "daemon-config.json"
DAEMON_CONFIG_BACKUP = "pre-vault/daemon-config.json"
#: Written by ``coffer migrate --rollback``; removed by ``--resume``.
HOLD_MARKER = "MIGRATION_ROLLED_BACK"
#: The record of the upgrade, read by ``--rollback``.
RECORD = "local/migration.json"
#: The previous build's sync working tree: left where it is, named in the report.
OLD_SYNC_TREE = "sync"
#: The old knowledge root's own history, folded into the vault repository.
OLD_KNOWLEDGE_GIT = "knowledge/.git"


def at(home: Path, rel: str) -> Path:
    """``~/.coffer/<rel>`` under ``home``."""
    return coffer_home(home) / rel


__all__ = [
    "BACKUP_DIR",
    "CLASS_DIRS",
    "DAEMON_CONFIG",
    "DAEMON_CONFIG_BACKUP",
    "DB_BACKUP",
    "HOLD_MARKER",
    "IN_PLACE",
    "KNOWLEDGE_GIT_BACKUP",
    "LAYOUT_REVISION",
    "LEGACY_DB",
    "OLD_KNOWLEDGE_GIT",
    "OLD_SYNC_TREE",
    "PRE_LAYOUT_REVISION",
    "RECORD",
    "RUNS_DB",
    "SIDE_FILES",
    "STAMPED_BACKUP",
    "TREE_MOVES",
    "at",
]
