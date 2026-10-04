"""``find_git`` / ``check_git`` against real executables on a made-up ``PATH``
(spec daemon "Wait in a setup state when git is missing or too old")."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from coffer.infrastructure.vault.git_requirement import check_git, find_git


def _fake_git(directory: Path, version: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    git = directory / "git"
    git.write_text(f'#!/bin/sh\necho "git version {version}"\n')
    git.chmod(0o755)
    return git


@pytest.mark.skipif(os.name == "nt", reason="a shell script stands in for git")
def test_find_git_reads_the_version_of_the_git_on_the_path(tmp_path: Path) -> None:
    git = _fake_git(tmp_path / "old", "2.30.1")
    found = find_git(str(git.parent))
    assert found is not None
    assert (found.path, found.version) == (str(git), (2, 30))
    assert find_git(str(tmp_path / "empty")) is None


@pytest.mark.skipif(os.name == "nt", reason="a shell script stands in for git")
def test_check_git_falls_back_to_the_login_shells_path(tmp_path: Path) -> None:
    old = _fake_git(tmp_path / "old", "2.30.1")
    new = _fake_git(tmp_path / "new", "2.45.0")
    check = check_git(daemon_path=str(old.parent), login_path=lambda: str(new.parent))
    assert check.ok and check.from_login_path
    assert check.usable is not None and check.usable.path == str(new)
