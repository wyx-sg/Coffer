"""Which ``git`` binary the vault runs (``infrastructure/vault/git.py``).

The ``git`` on ``PATH`` may be a launcher (Apple's ``/usr/bin/git`` looks up
the developer tools on every call); the vault asks it once for its exec path
and runs the binary there, falling back to plain ``git`` when the answer is
not usable."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from coffer.infrastructure.vault import git


def _script(folder: Path, name: str, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture(autouse=True)
def _fresh_lookup() -> None:
    git._executable.cache_clear()


def test_a_launcher_is_asked_once_for_the_binary_it_starts(tmp_path: Path) -> None:
    core = tmp_path / "libexec" / "git-core"
    real = _script(core, "git", 'echo "git version 9.9.9 (the real one)"')
    calls = tmp_path / "launcher-calls"
    _script(tmp_path / "bin", "git", f'echo x >> "{calls}"\necho "{core}"')
    search = str(tmp_path / "bin")
    assert git._executable(search) == str(real)
    assert git._executable(search) == str(real)
    assert calls.read_text().count("x") == 1  # cached per PATH


def test_a_launcher_whose_answer_holds_no_binary_falls_back_to_git(tmp_path: Path) -> None:
    _script(tmp_path / "bin", "git", f'echo "{tmp_path / "nowhere"}"')
    assert git._executable(str(tmp_path / "bin")) == "git"
    _script(tmp_path / "failing", "git", "exit 3")
    assert git._executable(str(tmp_path / "failing")) == "git"


def test_without_git_on_path_the_vault_reports_git_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert git._executable(os.environ["PATH"]) == "git"
    with pytest.raises(git.GitMissing):
        git.run(tmp_path, "--version")


def test_the_real_git_resolves_to_a_binary_that_runs(tmp_path: Path) -> None:
    resolved = git._executable(os.environ.get("PATH"))
    assert Path(resolved).is_absolute() and Path(resolved).name == "git"
    done = git.run(tmp_path, "--version")
    assert done.stdout.startswith(b"git version")
