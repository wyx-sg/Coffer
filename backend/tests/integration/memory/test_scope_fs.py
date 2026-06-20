"""Integration: git-root detection + knowledge-lane scan over a real directory."""

from __future__ import annotations

import pathlib
import subprocess

from coffer.domain.memory.fact import MemoryFact
from coffer.infrastructure.knowledge.paths import inbox_item_path, knowledge_dir
from coffer.infrastructure.memory.files import (
    legacy_root_facts,
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


def test_git_branch_reads_linked_worktree_branch(tmp_path: pathlib.Path) -> None:
    """A linked worktree's ``.git`` is a FILE (``gitdir: <path>``) pointing at
    the real gitdir; ``git_branch`` must follow it to read that worktree's HEAD.
    This exercises the ``.git``-is-a-file branch (SHOULD 2)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "work"], repo)
    _git(["config", "user.email", "test@coffer.local"], repo)
    _git(["config", "user.name", "Coffer Test"], repo)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(["add", "README.md"], repo)
    _git(["commit", "-q", "-m", "seed"], repo)
    # Add a real linked worktree on a NEW branch "feature".
    wt = tmp_path / "wt-feature"
    _git(["worktree", "add", "-q", "-b", "feature", str(wt)], repo)
    # The worktree's .git is a file, not a directory.
    assert (wt / ".git").is_file()
    assert git_branch(str(wt)) == "feature"
    # And from a subdirectory of the worktree too.
    sub = wt / "src"
    sub.mkdir()
    assert git_branch(str(sub)) == "feature"


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


def test_scan_reads_knowledge_inbox_recursively(tmp_path: pathlib.Path) -> None:
    store = tmp_path / "s"
    write_fact_file(inbox_item_path(store, "alpha-1"), _fact("1", "alpha", "the alpha"))
    write_fact_file(inbox_item_path(store, "beta-2"), _fact("2", "beta", "the beta"))
    # A hand-written topic doc at the knowledge root is also picked up.
    write_fact_file(knowledge_dir(store) / "topic.md", _fact("3", "topic", "a topic"))
    scan = scan_store_dir(store)
    assert set(scan.files) == {"1", "2", "3"}


def test_scan_excludes_index_md_and_missing_dir(tmp_path: pathlib.Path) -> None:
    store = tmp_path / "s"
    # No knowledge/ dir yet → empty scan, never raises.
    assert scan_store_dir(store).files == {}
    write_fact_file(inbox_item_path(store, "f-1"), _fact("1", "f", "d"))
    (knowledge_dir(store) / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    scan = scan_store_dir(store)
    assert set(scan.files) == {"1"}  # INDEX.md is not treated as a fact


def test_scan_ignores_legacy_root_facts(tmp_path: pathlib.Path) -> None:
    """Pre-lane facts at the store root are abandoned in place: not scanned (the
    scan reads only knowledge/), but discoverable via legacy_root_facts()."""
    store = tmp_path / "s"
    store.mkdir()
    write_fact_file(store / "old-fact.md", _fact("9", "old", "legacy"))
    (store / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    assert scan_store_dir(store).files == {}  # root facts not read
    legacy = legacy_root_facts(store)
    assert [p.name for p in legacy] == ["old-fact.md"]  # MEMORY.md excluded


def test_project_ulid_stable_across_calls_for_same_root(tmp_path: pathlib.Path) -> None:
    root = str(tmp_path / "repo")
    assert project_ulid(root) == project_ulid(root)
