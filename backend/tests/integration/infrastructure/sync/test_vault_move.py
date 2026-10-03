"""Moving the vault out of a synchronised folder (spec vault-sync "Move the
vault out of a synchronised folder"): the checks on the new folder, and a real
git vault carried across with its history intact."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from coffer.domain.sync.errors import (
    SyncVaultTargetInCloud,
    SyncVaultTargetInvalid,
    SyncVaultTargetNotEmpty,
)
from coffer.infrastructure.sync.vault_move import VaultMover


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return done.stdout


def _repo(root: Path) -> None:
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    (root / "knowledge").mkdir()
    (root / "knowledge" / "a.md").write_text("alpha\n")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "one")
    (root / "dirty.txt").write_text("uncommitted\n")  # status must survive the move


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / ".coffer").mkdir()
    return tmp_path


def _icloud_vault(home: Path) -> Path:
    real = home / "Library/Mobile Documents/com~apple~CloudDocs/Coffer"
    _repo(real)
    (home / ".coffer" / "vault").symlink_to(real, target_is_directory=True)
    return real


@pytest.mark.acceptance(
    spec="vault-sync", scenario="the vault is moved out of a synchronised folder"
)
def test_a_linked_icloud_vault_becomes_a_real_folder_at_its_own_path(home: Path) -> None:
    real = _icloud_vault(home)
    head = _git(real, "rev-parse", "HEAD")
    mover = VaultMover(home=home)
    assert mover.real_path() == str(real.resolve())
    assert mover.default_path() == str(home / ".coffer" / "vault")

    origin, target = mover.move(str(home / ".coffer" / "vault"))

    vault = home / ".coffer" / "vault"
    assert not vault.is_symlink() and (vault / "knowledge" / "a.md").read_text() == "alpha\n"
    assert _git(vault, "rev-parse", "HEAD") == head
    assert (vault / "dirty.txt").exists()
    assert (origin, target) == (str(real.resolve()), str(vault.resolve()))
    assert real.is_dir() and list(real.iterdir()) == []  # left empty for the person
    assert mover.real_path() == str(vault.resolve())


def test_a_real_vault_moves_elsewhere_and_its_own_path_leads_to_it(home: Path) -> None:
    vault = home / ".coffer" / "vault"
    _repo(vault)
    dest = home / "work" / "vault"
    dest.parent.mkdir()
    mover = VaultMover(home=home)

    mover.move(str(dest))

    assert vault.is_symlink() and vault.resolve() == dest.resolve()
    assert _git(vault, "log", "--format=%s") == "one\n"
    assert mover.real_path() == str(dest.resolve())


def test_a_target_inside_a_synchronised_folder_is_refused(home: Path) -> None:
    _repo(home / ".coffer" / "vault")
    for folder, tool in (
        (home / "Library/Mobile Documents/x", "iCloud Drive"),
        (home / "Library/CloudStorage/Dropbox/x", "a cloud drive"),
    ):
        folder.parent.mkdir(parents=True)
        with pytest.raises(SyncVaultTargetInCloud) as caught:
            VaultMover(home=home).move(str(folder))
        assert caught.value.tool == tool
    synced = home / "sync"
    synced.mkdir()
    (synced / ".stfolder").mkdir()
    with pytest.raises(SyncVaultTargetInCloud):
        VaultMover(home=home).move(str(synced / "vault"))


def test_a_target_that_is_not_free_is_refused(home: Path) -> None:
    vault = home / ".coffer" / "vault"
    _repo(vault)
    mover = VaultMover(home=home)
    full = home / "full"
    full.mkdir()
    (full / "x").write_text("x")
    with pytest.raises(SyncVaultTargetNotEmpty):
        mover.move(str(full))
    for bad in ("relative/path", "", str(vault), str(vault / "inner"), str(home), "/nope/a/b"):
        with pytest.raises(SyncVaultTargetInvalid):
            mover.move(bad)
    assert (vault / "knowledge" / "a.md").exists() and not vault.is_symlink()


def test_an_empty_existing_folder_is_taken(home: Path) -> None:
    vault = home / ".coffer" / "vault"
    _repo(vault)
    dest = home / "empty"
    dest.mkdir()
    VaultMover(home=home).move(str(dest))
    assert (dest / "knowledge" / "a.md").exists()


def test_across_filesystems_the_copy_is_verified_and_the_old_folder_emptied(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = _icloud_vault(home)

    def no_rename(self: Path, target: object) -> Path:
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(Path, "rename", no_rename)
    VaultMover(home=home).move(str(home / ".coffer" / "vault"))
    vault = home / ".coffer" / "vault"
    assert not vault.is_symlink() and (vault / "knowledge" / "a.md").exists()
    assert _git(vault, "log", "--format=%s") == "one\n"
    assert real.is_dir() and list(real.iterdir()) == []


def test_a_failed_move_leaves_the_vault_where_it_was(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coffer.domain.sync.errors import SyncVaultMoveFailed
    from coffer.infrastructure.sync import vault_move

    real = _icloud_vault(home)
    monkeypatch.setattr(vault_move, "_fingerprint", lambda root: (root.name,))
    with pytest.raises(SyncVaultMoveFailed):
        VaultMover(home=home).move(str(home / ".coffer" / "vault"))
    vault = home / ".coffer" / "vault"
    assert vault.is_symlink() and vault.resolve() == real.resolve()
    assert (real / "knowledge" / "a.md").exists()
