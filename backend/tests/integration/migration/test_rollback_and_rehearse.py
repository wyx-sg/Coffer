"""``coffer migrate --rollback`` restores the pre-upgrade home byte for byte,
holds it until ``--resume``; ``--rehearse`` runs both on a copy and leaves
the source untouched (ADR every-vault-file-carries-its-format-version
"Rollback of a migration is a restore, never a downgrade")."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from coffer.infrastructure.vault.home import coffer_home
from coffer.infrastructure.vault.migration.errors import (
    MigrationOnHold,
    MigrationRefused,
    MigrationRequired,
)
from coffer.infrastructure.vault.migration.guard import refuse_unmigrated_home
from coffer.infrastructure.vault.migration.rehearse import rehearse
from coffer.infrastructure.vault.migration.rollback import resume, rollback
from coffer.infrastructure.vault.migration.run import migrate
from coffer.infrastructure.vault.migration.verify import hash_tree, is_artifact, restored
from coffer.surfaces.cli.main import app as cli

from .conftest import UPGRADE
from .legacy_home import LegacyHome, build_legacy_home


def _migrate(home: Path):  # type: ignore[no-untyped-def]
    return migrate(home, upgrade_db=UPGRADE, build="test")


def _snapshot(legacy: LegacyHome) -> dict[str, str]:
    return {k: v for k, v in hash_tree(legacy.coffer).items() if not is_artifact(k)}


def test_rollback_gives_the_old_home_back_byte_for_byte(legacy: LegacyHome) -> None:
    before = _snapshot(legacy)
    _migrate(legacy.home)
    assert rollback(legacy.home) == []
    assert restored(before, legacy.home) == []
    marker = json.loads((legacy.coffer / "MIGRATION_ROLLED_BACK").read_text())
    aside = set(marker["set_aside"])
    assert any(n.startswith("vault.rolled-back-") for n in aside)
    assert any(n.startswith("local.rolled-back-") for n in aside)
    assert any(n.startswith("runs.db.rolled-back-") for n in aside)
    assert (legacy.coffer / "knowledge" / ".git" / "HEAD").is_file()


def test_what_was_written_after_the_upgrade_survives_in_the_set_aside_vault(
    legacy: LegacyHome,
) -> None:
    _migrate(legacy.home)
    note = legacy.coffer / "vault" / "knowledge" / "notes" / "after.md"
    note.write_text("written after the upgrade\n")
    rollback(legacy.home)
    # The tree it was written into went back to its old place, with it.
    assert (legacy.coffer / "knowledge" / "notes" / "after.md").is_file()
    kept = [p for p in legacy.coffer.iterdir() if p.name.startswith("vault.rolled-back-")]
    assert len(kept) == 1 and (kept[0] / ".git").is_dir()


def test_a_rolled_back_home_is_held_until_resume(legacy: LegacyHome) -> None:
    _migrate(legacy.home)
    rollback(legacy.home)
    with pytest.raises(MigrationOnHold, match="--resume"):
        refuse_unmigrated_home(legacy.home)
    with pytest.raises(MigrationOnHold):
        _migrate(legacy.home)
    with pytest.raises(MigrationRefused):
        rollback(legacy.home)
    assert resume(legacy.home) is True and resume(legacy.home) is False
    with pytest.raises(MigrationRequired, match="coffer migrate"):
        refuse_unmigrated_home(legacy.home)
    for aside in legacy.coffer.glob("*.rolled-back-*"):
        shutil.move(str(aside), str(legacy.home / aside.name))
    assert _migrate(legacy.home).outcome == "migrated", "the upgrade can be taken again"


def test_the_daemon_refuses_a_home_that_was_not_upgraded(legacy: LegacyHome) -> None:
    with pytest.raises(MigrationRequired, match="coffer migrate"):
        refuse_unmigrated_home(legacy.home)
    _migrate(legacy.home)
    refuse_unmigrated_home(legacy.home)


def test_an_upgrade_that_stopped_half_way_is_refused_and_rolled_back(
    legacy: LegacyHome, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _snapshot(legacy)
    from coffer.infrastructure.vault.migration import run

    def boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise RuntimeError("disk full")

    monkeypatch.setattr(run, "_commit_vault", boom)
    with pytest.raises(RuntimeError):
        _migrate(legacy.home)
    monkeypatch.undo()
    with pytest.raises(MigrationRefused, match="--rollback"):
        _migrate(legacy.home)
    rollback(legacy.home)
    assert restored(before, legacy.home) == []


def test_from_0114_the_upgrade_brings_the_database_forward_and_rollback_undoes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "old"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    legacy = build_legacy_home(home, revision="0114")
    before = _snapshot(legacy)
    report = _migrate(home)
    assert report.counts["tool reach overrides"] == 0
    features = json.loads((legacy.coffer / "daemon-config.json").read_text())["features"]
    assert features == {"other": 1}, "0116 stripped the graduated switches"
    rollback(home)
    assert restored(before, home) == []
    with sqlite3.connect(legacy.db) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0114",)


def test_a_fresh_install_gets_an_empty_vault_and_runs_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "fresh"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    assert _migrate(home).outcome == "fresh"
    assert (coffer_home(home) / "runs.db").is_file()
    assert (coffer_home(home) / "vault" / ".git").is_dir()
    assert _migrate(home).outcome == "already"


def test_rehearse_leaves_the_source_untouched_and_passes(legacy: LegacyHome) -> None:
    before = hash_tree(legacy.coffer)
    result = rehearse(legacy.home, upgrade_db=UPGRADE, build="test")
    assert result.report.outcome == "migrated"
    assert result.missing == [] and result.not_restored == [] and result.ok
    assert hash_tree(legacy.coffer) == before
    assert not (legacy.coffer / "vault" / ".git").exists()


def test_the_cli_rehearses_a_named_home(legacy: LegacyHome) -> None:
    before = hash_tree(legacy.coffer)
    done = CliRunner().invoke(cli, ["migrate", "--rehearse", "--home", str(legacy.home)])
    assert done.exit_code == 0, done.output
    assert "rehearsal passed" in done.output and "resources in vault: 11" in done.output
    assert hash_tree(legacy.coffer) == before


def test_the_cli_migrates_and_rolls_back(legacy: LegacyHome) -> None:
    runner = CliRunner()
    done = runner.invoke(cli, ["migrate"])
    assert done.exit_code == 0, done.output
    assert (legacy.coffer / "runs.db").is_file()
    done = runner.invoke(cli, ["migrate", "--rollback"])
    assert done.exit_code == 0, done.output
    done = runner.invoke(cli, ["migrate"])
    assert done.exit_code != 0 and "--resume" in done.output
    assert runner.invoke(cli, ["migrate", "--home", "/x"]).exit_code != 0
