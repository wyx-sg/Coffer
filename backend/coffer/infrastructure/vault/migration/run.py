"""``coffer migrate``: the one-time upgrade of a home to the vault layout
(plan q9 §3; ADR storage-is-five-classes-by-nature).

A person runs it once, with the daemon stopped; the daemon never migrates on
its own and refuses to start on a home that has not been upgraded
(``guard.refuse_unmigrated_home``). In order:

1. back up ``coffer.db`` (+``-wal``/``-shm``) as ``coffer.db.pre-vault`` and
   ``daemon-config.json`` into the backup set — first, before anything moves;
2. bring ``coffer.db`` to revision 0116 and read every table that moves out;
3. create the vault repository, move the trees into their class directories,
   fold the knowledge history in, strip the curation stamps;
4. write every resource, state document, ciphertext and local file, and
   commit the vault as **one** ``daemon`` commit (``Coffer-Layout: db -> 3``);
5. rename ``coffer.db`` to ``runs.db`` and upgrade it to head (revision 0136
   re-keys the history to uids and drops the moved tables).

``local/migration.json`` records every step as it happens, so
``coffer migrate --rollback`` (:mod:`.rollback`) undoes a finished upgrade
and a failed one alike. A home without ``coffer.db`` is a fresh install: it
gets an empty vault and ``runs.db``.

Everything runs with ``HOME`` pointed at the home being upgraded, because the
stores it writes through resolve their files from ``HOME`` — which is also
what keeps a rehearsal in a throwaway home away from the real one.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path

from coffer.domain.vault.writers import OP_LAYOUT, WRITER_DAEMON, CommitMeta
from coffer.infrastructure.vault.home import coffer_home, vault_root
from coffer.infrastructure.vault.instance import forget, vault_writer
from coffer.infrastructure.vault.migration import export_local, export_vault
from coffer.infrastructure.vault.migration.classes import storage_of as default_storage
from coffer.infrastructure.vault.migration.errors import MigrationOnHold, MigrationRefused
from coffer.infrastructure.vault.migration.export_vault import StorageOf
from coffer.infrastructure.vault.migration.knowledge import (
    fetch_history,
    fold_history,
    strip_stamps,
)
from coffer.infrastructure.vault.migration.legacy_db import LegacyState, read_legacy
from coffer.infrastructure.vault.migration.moves import links_into_old_trees, move_trees
from coffer.infrastructure.vault.migration.places import (
    CLASS_DIRS,
    DAEMON_CONFIG,
    DAEMON_CONFIG_BACKUP,
    DB_BACKUP,
    HOLD_MARKER,
    KNOWLEDGE_GIT_BACKUP,
    LEGACY_DB,
    OLD_SYNC_TREE,
    PRE_LAYOUT_REVISION,
    RUNS_DB,
    SIDE_FILES,
    at,
)
from coffer.infrastructure.vault.migration.record import Move, Record, RecordFile, now
from coffer.infrastructure.vault.migration.report import MigrationReport
from coffer.infrastructure.vault.migration.staging import LayoutCommit

#: ``upgrade_db(db_url, revision)``: run Alembic on one database. Supplied by
#: the caller (the CLI's composition root owns the migration runner).
UpgradeDb = Callable[[str, str], None]

LAYOUT_META = CommitMeta(
    writer=WRITER_DAEMON,
    operation=OP_LAYOUT,
    summary="Moved this vault out of coffer.db into files",
    layout="db -> 3",
)


def sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


@contextlib.contextmanager
def pointed_home(home: Path) -> Iterator[None]:
    """``HOME`` is ``home`` for the duration (see the module docstring)."""
    before = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = before


def _copy_db(source: Path, target: Path) -> None:
    shutil.copy2(source, target)
    for side in SIDE_FILES:
        companion = source.with_name(source.name + side)
        if companion.is_file():
            shutil.copy2(companion, target.with_name(target.name + side))


def _backup(home: Path, record: Record) -> None:
    _copy_db(at(home, LEGACY_DB), at(home, DB_BACKUP))
    record.database_backup = DB_BACKUP
    config = at(home, DAEMON_CONFIG)
    if config.is_file():
        target = at(home, DAEMON_CONFIG_BACKUP)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config, target)
        record.daemon_config_backup = True


def _rename_db(home: Path) -> None:
    """``coffer.db`` becomes ``runs.db``, with everything its WAL held."""
    legacy = at(home, LEGACY_DB)
    with contextlib.closing(sqlite3.connect(legacy)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for side in ("", *SIDE_FILES):
        source = legacy.with_name(legacy.name + side)
        if source.exists():
            source.rename(at(home, RUNS_DB + side))


def _check_home(home: Path) -> None:
    vault = vault_root(home)
    if (vault / ".git").exists() or at(home, "local").exists():
        raise MigrationRefused(
            f"{coffer_home(home)} already has a vault or local state but no runs.db — an "
            "upgrade that stopped half-way. Run `coffer migrate --rollback` first."
        )


def _export(
    txn: LayoutCommit, home: Path, state: LegacyState, storage_of: StorageOf
) -> dict[str, int]:
    counts = {
        f"resources in {cls}": n
        for cls, n in export_vault.write_resources(txn, home, state, storage_of).items()
    }
    counts["capability switch documents"] = export_vault.write_capability_switches(txn, home, state)
    counts["channel pairing documents"] = export_vault.write_channel_peers(txn, home, state)
    counts["engine settings documents"] = int(export_vault.write_engine_settings(txn, state))
    counts["secrets"] = export_local.write_secrets(txn, home, state)
    counts["secret boundary records"] = export_local.write_boundary(home, state)
    counts["tool reach overrides"] = export_vault.write_tool_reach(home, state)
    counts["retention policies"] = export_local.write_retention(state)
    counts["skill source statuses"] = export_local.write_source_status(state)
    counts["derived rows"] = export_local.write_derived(home, state)
    counts["sync remotes"] = int(export_local.write_sync_remote(state) is not None)
    return counts


def _commit_vault(home: Path, state: LegacyState, storage_of: StorageOf) -> dict[str, int]:
    """Every vault file — exported, moved in, stripped — as one commit."""
    staging = LayoutCommit(vault_writer(vault_root(home)).repo)
    counts = _export(staging, home, state, storage_of)
    staging.commit(LAYOUT_META)
    counts["vault files written"] = len(staging.paths)
    return counts


def _nested_repositories(home: Path) -> list[str]:
    root = vault_root(home)
    return sorted(
        f"{p.parent} has a git history of its own; its files are not recorded in the vault"
        for p in root.glob("*/**/.git")
        if not p.is_relative_to(root / ".git")
    )


def migrate(
    home: Path, *, upgrade_db: UpgradeDb, build: str, storage_of: StorageOf = default_storage
) -> MigrationReport:
    """Upgrade ``home`` (the parent of ``.coffer``) to the vault layout."""
    with pointed_home(home):
        marker = at(home, HOLD_MARKER)
        if marker.exists():
            raise MigrationOnHold(marker)
        runs, legacy = at(home, RUNS_DB), at(home, LEGACY_DB)
        if runs.exists():
            return MigrationReport("already")
        _check_home(home)
        forget(vault_root(home))
        if not legacy.exists():
            runs.parent.mkdir(parents=True, exist_ok=True)
            upgrade_db(sqlite_url(runs), "head")
            vault_writer(vault_root(home)).repo.ensure()
            return MigrationReport("fresh")
        record = Record(build=build, started_at=now())
        record.created = [d for d in CLASS_DIRS if not at(home, d).exists()]
        records = RecordFile(home)
        _backup(home, record)
        records.write(record)
        upgrade_db(sqlite_url(legacy), PRE_LAYOUT_REVISION)
        state = read_legacy(legacy)
        repo = vault_writer(vault_root(home)).repo
        remote = state.sync_remote
        repo.set_carry_secret(bool(remote and remote.get("include_credentials")))
        repo.ensure()

        def moved(move: Move) -> None:
            record.moves.append(move)
            records.write(record)

        move_trees(home, moved)
        old_git = vault_root(home) / "knowledge" / ".git"
        folded = 0
        if old_git.is_dir():
            folded = fold_history(repo) if fetch_history(repo, old_git) else 0
            target = at(home, KNOWLEDGE_GIT_BACKUP)
            target.parent.mkdir(parents=True, exist_ok=True)
            old_git.rename(target)
            record.knowledge_git = KNOWLEDGE_GIT_BACKUP
            records.write(record)
        record.stamped = strip_stamps(home, vault_root(home) / "knowledge")
        records.write(record)
        counts = _commit_vault(home, state, storage_of)
        counts["knowledge commits folded"] = folded
        counts["curation stamps stripped"] = len(record.stamped)
        report = MigrationReport("migrated", counts=counts, skipped=list(state.skipped))
        report.notices += _notices(home, state)
        _rename_db(home)
        record.database_renamed = True
        records.write(record)
        upgrade_db(sqlite_url(runs), "head")
        record.finished_at = now()
        records.write(record)
        return report


def _notices(home: Path, state: LegacyState) -> list[str]:
    notes = [
        f"link into a moved tree, left as it is: {link}" for link in links_into_old_trees(home)
    ]
    notes += _nested_repositories(home)
    if at(home, OLD_SYNC_TREE).exists():
        notes.append(
            f"the previous build's sync working tree {at(home, OLD_SYNC_TREE)} is left in "
            "place; nothing reads it any more"
        )
    if state.sync_remote is not None:
        notes.append(
            "the sync remote is kept but holds the previous layout: publish this vault to an "
            "empty branch or remote, and join every other machine to it as new after it "
            "migrates"
        )
    return notes


__all__ = ["LAYOUT_META", "UpgradeDb", "migrate", "pointed_home"]
