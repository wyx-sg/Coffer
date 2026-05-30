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
