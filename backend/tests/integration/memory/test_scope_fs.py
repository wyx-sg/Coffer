"""Integration: git-root detection + MEMORY.md regen over a real directory."""

from __future__ import annotations

import pathlib
import subprocess

import pytest

from coffer.domain.memory.fact import MemoryFact
from coffer.infrastructure.memory.files import (
    regenerate_memory_index,
    scan_store_dir,
    write_fact_file,
)
from coffer.infrastructure.memory.scope_fs import git_branch, git_root, project_ulid


def _git(args: list[str], cwd: pathlib.Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_git_branch_reads_current_branch(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "work"], repo)
    assert git_branch(str(repo)) == "work"
    # resolves from a subdirectory too
    sub = repo / "src"
    sub.mkdir()
    assert git_branch(str(sub)) == "work"


def test_git_branch_none_outside_repo(tmp_path: pathlib.Path) -> None:
    assert git_branch(str(tmp_path)) is None


def test_git_root_walks_up_to_dot_git(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    nested = repo / "src" / "pkg"
    nested.mkdir(parents=True)
    assert git_root(str(nested)) == repo.resolve()


def test_git_root_handles_worktree_file_marker(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "wt"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /elsewhere")  # worktree uses a file
    assert git_root(str(repo)) == repo.resolve()


def test_git_root_none_outside_repo(tmp_path: pathlib.Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert git_root(str(plain)) is None


def _fact(fact_id: str, name: str, desc: str) -> MemoryFact:
    from datetime import UTC, datetime

    now = datetime.now(tz=UTC)
    return MemoryFact(
        id=fact_id,
        name=name,
        description=desc,
        body=f"body for {name}",
        actor="user",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.acceptance(spec="007-memory", scenario="writing a fact regenerates MEMORY.md")
def test_regenerate_memory_index_is_idempotent(tmp_path: pathlib.Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    write_fact_file(store / "beta.md", _fact("2", "beta", "the beta"))
    write_fact_file(store / "alpha.md", _fact("1", "alpha", "the alpha"))
    first = regenerate_memory_index(store).read_text()
    second = regenerate_memory_index(store).read_text()
    assert first == second  # idempotent
    # Derived format, ordered by name.
    lines = [ln for ln in first.splitlines() if ln.startswith("- [")]
    assert lines[0].startswith("- [alpha](")
    assert "— the alpha" in lines[0]
    assert lines[1].startswith("- [beta](")


def test_scan_excludes_memory_index(tmp_path: pathlib.Path) -> None:
    store = tmp_path / "s"
    store.mkdir()
    write_fact_file(store / "f.md", _fact("1", "f", "d"))
    regenerate_memory_index(store)
    scan = scan_store_dir(store)
    assert set(scan.files) == {"1"}  # MEMORY.md not treated as a fact


def test_project_ulid_stable_across_calls_for_same_root(tmp_path: pathlib.Path) -> None:
    root = str(tmp_path / "repo")
    assert project_ulid(root) == project_ulid(root)
