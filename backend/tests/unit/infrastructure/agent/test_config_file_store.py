"""Unit tests for ConfigFileStore — the filesystem adapter for config files."""

from __future__ import annotations

import pathlib

from coffer.infrastructure.agent.config_file_store import ConfigFileStore


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
    assert (tmp_path / "config.toml.bak").read_text(encoding="utf-8") == "old = 1\n"


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
    assert (tmp_path / "a.md.bak").read_text() == "A"
    assert store.delete_with_backup(f) is False  # already gone


def test_fingerprint_stable_and_empty_for_missing() -> None:
    assert ConfigFileStore.fingerprint(None) == ""
    fp = ConfigFileStore.fingerprint("{}")
    assert fp == ConfigFileStore.fingerprint("{}") and len(fp) == 64
    assert ConfigFileStore.fingerprint("x") != fp
