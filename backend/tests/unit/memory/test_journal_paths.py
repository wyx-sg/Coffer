# backend/tests/unit/memory/test_journal_paths.py
"""Unit: journal lane path helpers."""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.knowledge.paths import journal_dir, journal_path


def test_journal_dir_is_store_root_subdir(tmp_path: pathlib.Path) -> None:
    assert journal_dir(tmp_path) == tmp_path / "journal"


def test_journal_path_is_period_file(tmp_path: pathlib.Path) -> None:
    assert journal_path(tmp_path, "2026-06") == tmp_path / "journal" / "2026-06.md"


def test_journal_path_rejects_traversal(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError):
        journal_path(tmp_path, "../escape")
