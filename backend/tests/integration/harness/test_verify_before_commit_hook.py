"""Integration tests for .claude/hooks/verify_before_commit.py.

The hook asks for confirmation when a `git commit` is about to run while
`make verify` is stale (source changed since the last passing verify). It must
stay silent for fresh trees, for any non-commit command, and when no verify
baseline exists yet (no stamp -> nothing to be stale against), and never break
the agent on error.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import HOOKS_DIR, REPO_ROOT

_HOOK = HOOKS_DIR / "verify_before_commit.py"
_VERIFY_STAMP = REPO_ROOT / "scripts" / "verify_stamp.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _run(command: str, project_dir: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)}
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env=env,
        timeout=60,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "mod.py").write_text("x = 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def _stamp(repo: Path) -> None:
    subprocess.run(["python3", str(_VERIFY_STAMP), "write"], cwd=str(repo), check=True)


def _decision(proc: subprocess.CompletedProcess[str]) -> str | None:
    out = proc.stdout.strip()
    if not out:
        return None
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"]


def test_silent_when_no_stamp_baseline(repo: Path) -> None:
    # No stamp means no `make verify` baseline exists yet (the stamp is
    # gitignored, so a fresh clone or new branch never has one). The guard stays
    # silent rather than nagging on every commit; it only asks once a baseline
    # exists and source has since changed (covered below).
    proc = _run("git commit -m 'wip'", repo)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ""  # no baseline -> no decision -> default flow


def test_asks_when_source_changed_since_verify(repo: Path) -> None:
    _stamp(repo)
    (repo / "mod.py").write_text("x = 2  # changed after verify\n")
    proc = _run("git commit -am 'change'", repo)
    assert _decision(proc) == "ask"


def test_silent_when_fresh(repo: Path) -> None:
    _stamp(repo)
    proc = _run("git commit -m 'verified'", repo)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ""  # no decision -> default flow


def test_silent_for_non_commit_commands(repo: Path) -> None:
    # No stamp at all, but these are not commits -> hook must not fire.
    for command in ["git status", "git add -A", "echo committing now", "ls"]:
        proc = _run(command, repo)
        assert proc.stdout.strip() == "", f"hook fired on {command!r}"


def test_survives_malformed_stdin(repo: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input="not json",
        capture_output=True,
        text=True,
        cwd=str(repo),
        timeout=60,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
