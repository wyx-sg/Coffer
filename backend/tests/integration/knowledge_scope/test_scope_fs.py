"""Integration: git-root detection + notes-lane scan over a real directory."""

from __future__ import annotations

import pathlib
import subprocess

from coffer.domain.knowledge.entry import KnowledgeEntry
from coffer.infrastructure.knowledge.paths import history_path, note_path, notes_dir
from coffer.infrastructure.knowledge_scope.files import (
    legacy_root_facts,
    scan_scope_dir,
    write_fact_file,
)
from coffer.infrastructure.knowledge_scope.scope_fs import git_root, project_ulid


def test_git_root_walks_up_to_dot_git(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    nested = repo / "src" / "pkg"
    nested.mkdir(parents=True)
    assert git_root(str(nested)) == repo.resolve()


def test_git_root_keeps_identity_for_unresolvable_gitfile(tmp_path: pathlib.Path) -> None:
    """A ``.git`` FILE whose gitdir has no ``commondir`` (a submodule, or a
    dangling pointer) is NOT a linked worktree — keep the dir's own identity."""
    repo = tmp_path / "wt"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /elsewhere")  # no commondir at target
    assert git_root(str(repo)) == repo.resolve()


def test_git_root_keeps_identity_for_submodule(tmp_path: pathlib.Path) -> None:
    """A submodule's ``.git`` FILE points at ``<super>/.git/modules/<name>``,
    a full gitdir with NO ``commondir`` file — a submodule is its own project
    and must keep its own identity, not collapse into the superproject."""
    mod = tmp_path / "mod"
    mod.mkdir()
    gitdir = tmp_path / "super" / ".git" / "modules" / "mod"
    gitdir.mkdir(parents=True)
    (mod / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    assert git_root(str(mod)) == mod.resolve()


def _git(args: list[str], cwd: pathlib.Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _seed_repo(repo: pathlib.Path, branch: str = "main") -> None:
    repo.mkdir(parents=True)
    _git(["init", "-q", "-b", branch], repo)
    _git(["config", "user.email", "test@coffer.local"], repo)
    _git(["config", "user.name", "Coffer Test"], repo)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(["add", "README.md"], repo)
    _git(["commit", "-q", "-m", "seed"], repo)


def test_git_root_collapses_linked_worktree_to_main_repo(tmp_path: pathlib.Path) -> None:
    """The core fix: a linked worktree resolves to the MAIN repo toplevel, so the
    same repo checked out in different worktrees is ONE project, not several."""
    repo = tmp_path / "repo"
    _seed_repo(repo)
    wt = tmp_path / "wt-feature"
    _git(["worktree", "add", "-q", "-b", "feature", str(wt)], repo)
    assert (wt / ".git").is_file()
    # git_root of the worktree collapses to the main repo toplevel...
    assert git_root(str(wt)) == repo.resolve()
    # ...including from a nested subdirectory of the worktree
    sub = wt / "src" / "pkg"
    sub.mkdir(parents=True)
    assert git_root(str(sub)) == repo.resolve()
    # ...so the worktree and the main checkout share ONE project identity
    assert project_ulid(git_root(str(wt))) == project_ulid(git_root(str(repo)))


def test_two_worktrees_share_one_project_identity(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    _seed_repo(repo)
    wt_a = tmp_path / "wt-a"
    wt_b = tmp_path / "wt-b"
    _git(["worktree", "add", "-q", "-b", "a", str(wt_a)], repo)
    _git(["worktree", "add", "-q", "-b", "b", str(wt_b)], repo)
    assert git_root(str(wt_a)) == repo.resolve()
    assert git_root(str(wt_b)) == repo.resolve()
    assert project_ulid(git_root(str(wt_a))) == project_ulid(git_root(str(wt_b)))


def test_git_root_none_outside_repo(tmp_path: pathlib.Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert git_root(str(plain)) is None


def _fact(fact_id: str, name: str, desc: str) -> KnowledgeEntry:
    from datetime import UTC, datetime

    now = datetime.now(tz=UTC)
    return KnowledgeEntry(
        id=fact_id,
        title=name,
        description=desc,
        body=f"body for {name}",
        actor="user",
        created_at=now,
        updated_at=now,
    )


def test_scan_reads_the_notes_lane_recursively(tmp_path: pathlib.Path) -> None:
    store = tmp_path / "s"
    write_fact_file(note_path(store, "alpha-1"), _fact("1", "alpha", "the alpha"))
    write_fact_file(note_path(store, "beta-2"), _fact("2", "beta", "the beta"))
    # The lane is flat by convention, but a hand-made subdirectory still indexes.
    write_fact_file(notes_dir(store) / "sub" / "gamma-3.md", _fact("3", "gamma", "a gamma"))
    scan = scan_scope_dir(store)
    assert set(scan.files) == {"1", "2", "3"}
    assert scan.files["1"].fact.title == "alpha"
    assert scan.files["1"].path == note_path(store, "alpha-1")


def test_scan_is_empty_before_the_lane_exists(tmp_path: pathlib.Path) -> None:
    store = tmp_path / "s"
    # No notes/ lane yet (a scope nobody has written to) → empty, never raises.
    assert scan_scope_dir(store).files == {}


def test_scan_skips_hidden_files_and_the_history_archive(tmp_path: pathlib.Path) -> None:
    """The archive must never re-enter the index as a duplicate of the note that
    replaced it, and the atomic writer's dot-prefixed temp files must not race
    the scan — ``pathlib`` globs match both, so the scan filters them."""
    store = tmp_path / "s"
    write_fact_file(note_path(store, "live-1"), _fact("1", "live", "the live one"))
    # A superseded revision, parked in the hidden sibling archive.
    write_fact_file(history_path(store, "live-1-20260101T000000"), _fact("1", "old", "superseded"))
    # A half-written temp file sitting in the lane itself.
    write_fact_file(notes_dir(store) / ".live-1.md.tmp.md", _fact("2", "tmp", "half written"))
    scan = scan_scope_dir(store)
    assert set(scan.files) == {"1"}
    assert scan.files["1"].fact.description == "the live one"  # the live copy, not the archive


def test_scan_ignores_legacy_root_facts(tmp_path: pathlib.Path) -> None:
    """Pre-lane facts at the store root are abandoned in place: not scanned (the
    scan reads only notes/), but discoverable via legacy_root_facts()."""
    store = tmp_path / "s"
    store.mkdir()
    write_fact_file(store / "old-fact.md", _fact("9", "old", "legacy"))
    write_fact_file(note_path(store, "current-1"), _fact("1", "current", "in the lane"))
    assert set(scan_scope_dir(store).files) == {"1"}  # root facts not read
    legacy = legacy_root_facts(store)
    assert [p.name for p in legacy] == ["old-fact.md"]  # lane files are not "legacy"


def test_project_ulid_stable_across_calls_for_same_root(tmp_path: pathlib.Path) -> None:
    root = str(tmp_path / "repo")
    assert project_ulid(root) == project_ulid(root)
