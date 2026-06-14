"""Tests for scripts/verify_stamp.py — the verify-before-commit freshness stamp.

`make verify` writes a content fingerprint of the repo's source; the
verify-before-commit hook compares it to commit-time content to decide whether
`make verify` is stale. The fingerprint must change when source content changes
but stay stable across `git add` (staging is not a content change).
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "verify_stamp.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_stamp", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "mod.py").write_text("x = 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def test_write_then_fresh(repo: Path) -> None:
    vs = _load()
    vs.write_stamp(repo)
    assert (repo / ".coffer-verify.stamp").exists()
    assert vs.is_fresh(repo) is True


def test_stale_after_source_edit(repo: Path) -> None:
    vs = _load()
    vs.write_stamp(repo)
    (repo / "mod.py").write_text("x = 2  # changed\n")
    assert vs.is_fresh(repo) is False


def test_fresh_is_stable_across_git_add(repo: Path) -> None:
    """Staging a new source file does not change its content, so a stamp taken
    after the file exists stays fresh through `git add` — the common
    verify-then-stage-then-commit flow must not trip the guard."""
    vs = _load()
    (repo / "new.py").write_text("y = 9\n")  # exists on disk (untracked)
    vs.write_stamp(repo)
    _git(repo, "add", "-A")  # stage it — content unchanged
    assert vs.is_fresh(repo) is True


def test_stale_when_no_stamp(repo: Path) -> None:
    vs = _load()
    assert vs.is_fresh(repo) is False


def test_non_source_change_does_not_stale(repo: Path) -> None:
    """A docs/text edit is not gated by `make verify`, so it must not flip the
    fingerprint (keeps the guard from nagging on doc-only commits)."""
    vs = _load()
    (repo / "NOTES.txt").write_text("just notes\n")
    vs.write_stamp(repo)
    (repo / "NOTES.txt").write_text("more notes\n")
    assert vs.is_fresh(repo) is True


def test_cli_check_exit_codes(repo: Path) -> None:
    fresh = subprocess.run(
        ["python3", str(_SCRIPT), "write"], cwd=str(repo), capture_output=True, text=True
    )
    assert fresh.returncode == 0
    ok = subprocess.run(
        ["python3", str(_SCRIPT), "check"], cwd=str(repo), capture_output=True, text=True
    )
    assert ok.returncode == 0
    (repo / "mod.py").write_text("x = 99\n")
    stale = subprocess.run(
        ["python3", str(_SCRIPT), "check"], cwd=str(repo), capture_output=True, text=True
    )
    assert stale.returncode == 1
