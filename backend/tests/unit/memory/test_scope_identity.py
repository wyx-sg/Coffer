"""Machine-portable project identity (spec 007 FR-004a, ADR-043)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from coffer.infrastructure.memory.scope_fs import (
    normalize_remote_url,
    origin_remote_url,
    project_identity,
    project_ulid,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(path: Path, remote: str | None) -> Path:
    path.mkdir(parents=True)
    _git(path, "init")
    if remote:
        _git(path, "remote", "add", "origin", remote)
    return path


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:Wyx-sg/Coffer.git", "github.com/wyx-sg/coffer"),
        ("https://github.com/wyx-sg/coffer", "github.com/wyx-sg/coffer"),
        ("https://user@github.com/wyx-sg/coffer.git", "github.com/wyx-sg/coffer"),
        ("ssh://git@github.com/wyx-sg/Coffer.git", "github.com/wyx-sg/coffer"),
        ("git://github.com/wyx-sg/coffer.git", "github.com/wyx-sg/coffer"),
        ("https://git.example.com:8443/team/repo/", "git.example.com:8443/team/repo"),
    ],
)
def test_normalize_remote_url(url: str, expected: str) -> None:
    assert normalize_remote_url(url) == expected


def test_same_remote_same_identity_across_paths(tmp_path) -> None:  # type: ignore[no-untyped-def]
    a = _repo(tmp_path / "users" / "alice" / "coffer", "git@github.com:me/coffer.git")
    b = _repo(tmp_path / "home" / "bob" / "src" / "coffer", "https://github.com/me/Coffer")
    assert project_identity(a) == project_identity(b)
    assert project_identity(a) != project_ulid(a)  # remote-derived, not path


def test_no_remote_falls_back_to_path_hash(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = _repo(tmp_path / "island", None)
    assert project_identity(repo) == project_ulid(repo)


def test_origin_url_readable_from_linked_worktree(tmp_path) -> None:  # type: ignore[no-untyped-def]
    main = _repo(tmp_path / "main", "git@github.com:me/coffer.git")
    (main / "f.txt").write_text("x", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "c")
    wt = tmp_path / "wt"
    _git(main, "worktree", "add", str(wt))
    assert origin_remote_url(wt) == "git@github.com:me/coffer.git"
    assert project_identity(wt) == project_identity(main)


def test_outside_git_returns_none(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert origin_remote_url(tmp_path) is None
