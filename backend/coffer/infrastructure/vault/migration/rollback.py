"""``coffer migrate --rollback`` and ``--resume`` (ADR
every-vault-file-carries-its-format-version "Rollback of a migration is a
restore, never a downgrade").

A rollback is a restore of what the upgrade kept, never a reverse
migration: the stamped knowledge documents and the knowledge history come
back out of the backup set, every recorded move is renamed back, the vault
repository and ``local/`` are moved aside as ``vault.rolled-back-<time>`` and
``local.rolled-back-<time>`` — so anything written after the upgrade
survives in that repository's history for a person to re-apply — ``runs.db``
is moved aside, and ``coffer.db`` and ``daemon-config.json`` are put back
from their backups. Then the hold marker is written: this build neither
starts on the home nor migrates it again until ``--resume`` removes it, so
the previous build can be installed and run on the restored home.

It works on a failed upgrade as well as a finished one, because the record
lists only what was actually done.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import forget
from coffer.infrastructure.vault.migration.errors import MigrationRefused
from coffer.infrastructure.vault.migration.knowledge import restore_stamps
from coffer.infrastructure.vault.migration.moves import reverse_moves
from coffer.infrastructure.vault.migration.places import (
    CLASS_DIRS,
    DAEMON_CONFIG,
    DAEMON_CONFIG_BACKUP,
    HOLD_MARKER,
    IN_PLACE,
    KNOWLEDGE_GIT_BACKUP,
    LEGACY_DB,
    RUNS_DB,
    SIDE_FILES,
    at,
)
from coffer.infrastructure.vault.migration.record import RecordFile, now
from coffer.infrastructure.vault.migration.run import pointed_home


def _stamp() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def _aside(path: Path, ts: str) -> Path | None:
    """Rename ``path`` to ``<name>.rolled-back-<ts>``; ``None`` if absent."""
    if not path.exists() and not path.is_symlink():
        return None
    target = path.with_name(f"{path.name}.rolled-back-{ts}")
    path.rename(target)
    return target


def _empty_tree(path: Path) -> bool:
    return path.is_dir() and not any(p.is_file() or p.is_symlink() for p in path.rglob("*"))


def _restore_db(home: Path, backup: str, ts: str, aside: list[str]) -> None:
    for side in ("", *SIDE_FILES):
        moved = _aside(at(home, RUNS_DB + side), ts)
        if moved is not None:
            aside.append(moved.name)
    legacy = at(home, LEGACY_DB)
    for side in ("", *SIDE_FILES):
        moved = _aside(legacy.with_name(legacy.name + side), ts)
        if moved is not None:
            aside.append(moved.name)
    source = at(home, backup)
    shutil.copy2(source, legacy)
    for side in SIDE_FILES:
        companion = source.with_name(source.name + side)
        if companion.is_file():
            shutil.copy2(companion, legacy.with_name(legacy.name + side))


def rollback(home: Path) -> list[str]:
    """Restore ``home`` to what it was before the upgrade; answer what could
    not be put back exactly (each left where it is, never deleted)."""
    with pointed_home(home):
        if at(home, HOLD_MARKER).exists():
            raise MigrationRefused("this home is already rolled back")
        record = RecordFile(home).read()
        if record is None:
            raise MigrationRefused("no upgrade is recorded in this home; nothing to roll back")
        ts = _stamp()
        problems: list[str] = []
        aside: list[str] = []
        knowledge = vault_root(home) / "knowledge"
        problems += restore_stamps(home, knowledge, record.stamped)
        if record.knowledge_git and at(home, KNOWLEDGE_GIT_BACKUP).is_dir():
            if knowledge.is_dir() and not (knowledge / ".git").exists():
                at(home, KNOWLEDGE_GIT_BACKUP).rename(knowledge / ".git")
            else:
                problems.append(f"the knowledge history stays at {at(home, KNOWLEDGE_GIT_BACKUP)}")
        problems += reverse_moves(home, record.moves)
        forget(vault_root(home))
        for name in ("vault", "local"):
            moved = _aside(at(home, name), ts)
            if moved is not None:
                aside.append(moved.name)
        # A tree the previous layout already kept inside ``vault/`` goes back
        # there: the previous build reads it at that path.
        for rel in IN_PLACE if "vault" not in record.created else ():
            kept = at(home, rel.replace("vault/", f"vault.rolled-back-{ts}/", 1))
            if kept.exists():
                at(home, rel).parent.mkdir(parents=True, exist_ok=True)
                kept.rename(at(home, rel))
        for name in CLASS_DIRS:
            path = at(home, name)
            if name in ("vault", "local") or name not in record.created or not path.exists():
                continue
            if _empty_tree(path):
                shutil.rmtree(path)
            else:
                moved = _aside(path, ts)
                if moved is not None:
                    aside.append(moved.name)
        if record.database_backup:
            _restore_db(home, record.database_backup, ts, aside)
        if record.daemon_config_backup and at(home, DAEMON_CONFIG_BACKUP).is_file():
            shutil.copy2(at(home, DAEMON_CONFIG_BACKUP), at(home, DAEMON_CONFIG))
        marker = {"rolled_back_at": now(), "set_aside": aside, "problems": problems}
        at(home, HOLD_MARKER).write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
        return problems


def resume(home: Path) -> bool:
    """Lift the hold a rollback left; ``False`` when there was none."""
    marker = at(home, HOLD_MARKER)
    if not marker.exists():
        return False
    marker.unlink()
    return True


__all__ = ["resume", "rollback"]
