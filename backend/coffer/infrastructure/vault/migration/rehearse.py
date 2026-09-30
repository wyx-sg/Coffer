"""``coffer migrate --rehearse``: the upgrade and its rollback, on a copy
(ADR every-vault-file-carries-its-format-version: "``coffer migrate
--rehearse`` runs the migration against a copy in an isolated ``HOME`` and
reports the difference").

The source home's ``.coffer`` is copied byte for byte — only read, never
opened by SQLite — into a temporary home; the upgrade runs there in this
process, its result is checked against an inventory taken first, the copy is
rolled back and compared with what it was, and the copy is deleted. The
source is never written: the daemon should still be stopped, so the copy is
not taken half-way through one of its writes.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from coffer.infrastructure.vault.home import coffer_home, vault_root
from coffer.infrastructure.vault.instance import forget
from coffer.infrastructure.vault.migration.classes import storage_of as default_storage
from coffer.infrastructure.vault.migration.export_vault import StorageOf
from coffer.infrastructure.vault.migration.report import MigrationReport
from coffer.infrastructure.vault.migration.rollback import rollback
from coffer.infrastructure.vault.migration.run import UpgradeDb, migrate, pointed_home
from coffer.infrastructure.vault.migration.verify import check, hash_tree, restored, take_inventory

#: Never copied: the running daemon's rendezvous (a rehearsal must not look
#: like a second daemon) and sockets.
_NOT_COPIED = ("daemon.json",)


@dataclass
class Rehearsal:
    report: MigrationReport
    #: What the upgraded copy lacked compared with the source.
    missing: list[str] = field(default_factory=list)
    #: How the rolled-back copy differed from the source.
    not_restored: list[str] = field(default_factory=list)
    #: What the rollback itself could not put back.
    rollback_problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.not_restored)


def _copy(source: Path, target: Path) -> None:
    def ignore(directory: str, names: list[str]) -> list[str]:
        return [n for n in names if n in _NOT_COPIED or (Path(directory) / n).is_socket()]

    shutil.copytree(source, target, symlinks=True, ignore=ignore)


def rehearse(
    source_home: Path,
    *,
    upgrade_db: UpgradeDb,
    build: str,
    storage_of: StorageOf = default_storage,
    scratch: Path | None = None,
) -> Rehearsal:
    """Rehearse the upgrade of ``source_home`` (the parent of ``.coffer``)."""
    source = coffer_home(source_home)
    if not source.is_dir():
        raise FileNotFoundError(f"{source} does not exist")
    work = Path(tempfile.mkdtemp(prefix="coffer-rehearse-", dir=scratch))
    try:
        home = work / "home"
        home.mkdir()
        _copy(source, coffer_home(home))
        before = hash_tree(coffer_home(home))
        with pointed_home(home):
            inventory = take_inventory(home)
        report = migrate(home, upgrade_db=upgrade_db, storage_of=storage_of, build=build)
        result = Rehearsal(report=report)
        if report.outcome == "migrated":
            result.missing = check(home, inventory)
            result.rollback_problems = rollback(home)
            result.not_restored = restored(before, home)
        return result
    finally:
        forget(vault_root(work / "home"))
        shutil.rmtree(work, ignore_errors=True)


__all__ = ["Rehearsal", "rehearse"]
