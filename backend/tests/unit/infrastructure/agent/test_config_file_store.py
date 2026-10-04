"""Unit tests for ConfigFileStore — the filesystem adapter for config files."""

from __future__ import annotations

import pathlib
import re

import pytest

from coffer.domain.workspace_errors import ConfigFileStale
from coffer.infrastructure.agent.config_file_store import ConfigFileStore, backup_dir_for
from coffer.infrastructure.vault.home import config_backups_dir


def test_read_text_returns_content(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    assert ConfigFileStore().read_text(p) == '{"a": 1}'


def test_read_text_missing_returns_none(tmp_path: pathlib.Path) -> None:
    assert ConfigFileStore().read_text(tmp_path / "nope.json") is None


def test_read_text_directory_returns_none(tmp_path: pathlib.Path) -> None:
    """A directory where a config file is expected reports as absent (None),
    not an IsADirectoryError that would surface as a 500 — consistent with
    stat()'s is_file() check."""
    d = tmp_path / "CLAUDE.md"
    d.mkdir()
    assert ConfigFileStore().read_text(d) is None


def test_stat_directory_returns_none(tmp_path: pathlib.Path) -> None:
    d = tmp_path / "settings.json"
    d.mkdir()
    assert ConfigFileStore().stat(d) is None


def test_write_atomic_keeps_backup(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text("old = 1\n", encoding="utf-8")
    ConfigFileStore().write_text_atomic(p, "new = 2\n")
    assert p.read_text(encoding="utf-8") == "new = 2\n"
    latest = ConfigFileStore().latest_backup(p)
    assert latest is not None and latest.read_text(encoding="utf-8") == "old = 1\n"
    assert not (tmp_path / "config.toml.bak").exists()


def test_list_dir_recursive_md_only(tmp_path: pathlib.Path) -> None:
    store = ConfigFileStore()
    root = tmp_path / "agents"
    (root / "team").mkdir(parents=True)
    (root / "a.md").write_text("A")
    (root / "team" / "b.md").write_text("B")
    (root / "notes.txt").write_text("ignored")
    listed = store.list_dir(root)
    assert [(e.relpath, e.size) for e in listed] == [("a.md", 1), ("team/b.md", 1)]
    assert all(e.modified_at is not None for e in listed)


def test_list_dir_missing_returns_none(tmp_path: pathlib.Path) -> None:
    assert ConfigFileStore().list_dir(tmp_path / "missing") is None


def test_list_dir_skips_symlinked_files(tmp_path: pathlib.Path) -> None:
    store = ConfigFileStore()
    root = tmp_path / "agents"
    root.mkdir()
    real = tmp_path / "outside.md"
    real.write_text("X")
    (root / "link.md").symlink_to(real)
    assert store.list_dir(root) == []


def test_delete_with_backup(tmp_path: pathlib.Path) -> None:
    store = ConfigFileStore()
    f = tmp_path / "a.md"
    f.write_text("A")
    assert store.delete_with_backup(f) is True
    assert not f.exists()
    latest = store.latest_backup(f)
    assert latest is not None and latest.read_text() == "A"
    assert not (tmp_path / "a.md.bak").exists()
    assert store.delete_with_backup(f) is False  # already gone


def test_fingerprint_stable_and_empty_for_missing() -> None:
    assert ConfigFileStore.fingerprint(None) == ""
    fp = ConfigFileStore.fingerprint("{}")
    assert fp == ConfigFileStore.fingerprint("{}") and len(fp) == 64
    assert ConfigFileStore.fingerprint("x") != fp


# --------------------------------------------------------------------------- #
# optimistic concurrency + backup rotation                                     #
# --------------------------------------------------------------------------- #


def test_write_with_matching_fingerprint_succeeds(tmp_path: pathlib.Path) -> None:
    store = ConfigFileStore()
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    seen = store.fingerprint(store.read_text(p))
    store.write_text_atomic(p, '{"a": 1}', expected_fingerprint=seen)
    assert p.read_text(encoding="utf-8") == '{"a": 1}'


def test_write_refuses_when_the_file_changed_since_it_was_read(
    tmp_path: pathlib.Path,
) -> None:
    """The user's editor saved between Coffer's read and its write: the write
    must refuse rather than overwrite that edit, and leave the file as is."""
    store = ConfigFileStore()
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    seen = store.fingerprint(store.read_text(p))
    p.write_text('{"theme": "dark"}', encoding="utf-8")  # the concurrent edit

    with pytest.raises(ConfigFileStale) as exc:
        store.write_text_atomic(p, '{"a": 1}', expected_fingerprint=seen)

    assert exc.value.key == str(p)
    assert p.read_text(encoding="utf-8") == '{"theme": "dark"}'
    assert store.latest_backup(p) is None, "a refused write backs up nothing"


def test_write_refuses_when_a_file_appeared_since_the_absent_read(
    tmp_path: pathlib.Path,
) -> None:
    store = ConfigFileStore()
    p = tmp_path / "settings.json"
    seen = store.fingerprint(store.read_text(p))  # "" — absent
    assert seen == ""
    p.write_text('{"theme": "dark"}', encoding="utf-8")
    with pytest.raises(ConfigFileStale):
        store.write_text_atomic(p, "{}", expected_fingerprint=seen)


def test_write_without_fingerprint_is_unconditional(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    ConfigFileStore().write_text_atomic(p, '{"a": 1}')
    assert p.read_text(encoding="utf-8") == '{"a": 1}'


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="a config write leaves its backup in Coffer's folder and nothing beside the file",
)
def test_backups_land_in_coffers_folder_one_timestamped_file_per_write(
    tmp_path: pathlib.Path,
) -> None:
    store = ConfigFileStore()
    p = tmp_path / "agent" / "config.toml"
    p.parent.mkdir()
    p.write_text("v0\n", encoding="utf-8")
    for i in range(1, 5):
        store.write_text_atomic(p, f"v{i}\n")

    assert p.read_text(encoding="utf-8") == "v4\n"
    folder = backup_dir_for(p)
    assert folder.parent == config_backups_dir()
    assert folder.name.startswith("config.toml-")
    backups = sorted(folder.iterdir())
    assert [b.read_text(encoding="utf-8") for b in backups] == ["v0\n", "v1\n", "v2\n", "v3\n"]
    assert all(re.fullmatch(r"\d{8}T\d{12}Z(-\d+)?\.toml", b.name) for b in backups)
    latest = store.latest_backup(p)
    assert latest == backups[-1]
    assert latest.read_text(encoding="utf-8") == "v3\n"
    # Nothing is written next to the agent's file, and the folder is private.
    assert [c.name for c in p.parent.iterdir()] == ["config.toml"]
    assert (folder.stat().st_mode & 0o777) == 0o700
    assert (latest.stat().st_mode & 0o777) == 0o600


def test_same_name_in_two_places_gets_two_folders(tmp_path: pathlib.Path) -> None:
    store = ConfigFileStore()
    a, b = tmp_path / "a" / "settings.json", tmp_path / "b" / "settings.json"
    for f, text in ((a, "A"), (b, "B")):
        f.parent.mkdir()
        f.write_text(text)
        store.write_text_atomic(f, "new")
    assert backup_dir_for(a) != backup_dir_for(b)
    assert store.latest_backup(a).read_text() == "A"  # type: ignore[union-attr]
    assert store.latest_backup(b).read_text() == "B"  # type: ignore[union-attr]


def test_a_first_write_makes_no_backup(tmp_path: pathlib.Path) -> None:
    store = ConfigFileStore()
    p = tmp_path / "new.json"
    store.write_text_atomic(p, "{}")
    assert store.latest_backup(p) is None


def test_delete_backs_up_after_a_write_too(tmp_path: pathlib.Path) -> None:
    store = ConfigFileStore()
    p = tmp_path / "a.md"
    p.write_text("first")
    store.write_text_atomic(p, "second")
    assert store.delete_with_backup(p) is True
    texts = [b.read_text() for b in sorted(backup_dir_for(p).iterdir())]
    assert texts == ["first", "second"]
    assert [c.name for c in tmp_path.iterdir()] == []
