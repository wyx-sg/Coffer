"""What the tree mirror will and will not carry.

Spec vault-sync "Converge knowledge files and the skill store".

The mirrored trees are the vault's own directories, so almost everything under
them is source of truth — but not a symlink, whose target is not the vault's,
and not a nested ``.git``, which is another repository's internals. Both are
left out of the working tree and reported, never followed.
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.tree_mirror import _mirror_tree, _tree_files


def _write(root: pathlib.Path, rel: str, text: str = "x\n") -> pathlib.Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_tree_files_lists_regular_files_including_hidden_ones(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "notes/a.md")
    _write(tmp_path, "notes/.raw/a.html")
    _write(tmp_path, ".history/a.md")

    assert {p.as_posix() for p in _tree_files(tmp_path)} == {
        "notes/a.md",
        "notes/.raw/a.html",
        ".history/a.md",
    }


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a symlink in the vault is skipped rather than published",
)
def test_symlinks_are_skipped_not_followed(tmp_path: pathlib.Path) -> None:
    outside = _write(tmp_path / "outside", "secret.txt", "not vault content\n")
    live = tmp_path / "live"
    _write(live, "notes/kept.md")
    (live / "notes" / "leak.md").symlink_to(outside)
    (live / "linked-dir").symlink_to(tmp_path / "outside", target_is_directory=True)

    skipped: list[str] = []
    files = _tree_files(live, skipped)

    assert {p.as_posix() for p in files} == {"notes/kept.md"}
    assert sorted(skipped) == ["linked-dir", "notes/leak.md"]


def test_a_nested_git_directory_is_skipped(tmp_path: pathlib.Path) -> None:
    live = tmp_path / "live"
    _write(live, "skills/demo/SKILL.md")
    _write(live, "skills/demo/.git/HEAD", "ref: refs/heads/main\n")
    _write(live, "skills/demo/.git/objects/ab/cd")

    skipped: list[str] = []
    files = _tree_files(live, skipped)

    assert {p.as_posix() for p in files} == {"skills/demo/SKILL.md"}
    assert skipped == ["skills/demo/.git"]


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a symlink in the vault is skipped rather than published",
)
def test_mirror_tree_never_copies_a_symlink_target_and_reports_it(
    tmp_path: pathlib.Path,
) -> None:
    outside = _write(tmp_path / "outside", "secret.txt", "not vault content\n")
    live = tmp_path / "live"
    _write(live, "notes/kept.md", "kept\n")
    (live / "notes" / "leak.md").symlink_to(outside)
    dst = tmp_path / "worktree" / "knowledge"

    skipped = _mirror_tree(live, dst)

    assert (dst / "notes" / "kept.md").read_text() == "kept\n"
    assert not (dst / "notes" / "leak.md").exists()
    assert skipped == ["notes/leak.md"]


def test_a_symlink_already_in_the_destination_is_not_treated_as_a_file(
    tmp_path: pathlib.Path,
) -> None:
    """A link the working tree somehow holds is neither compared nor unlinked:
    the mirror sees only regular files on both sides."""
    live = tmp_path / "live"
    _write(live, "a.md", "a\n")
    dst = tmp_path / "dst"
    dst.mkdir()
    target = _write(tmp_path, "elsewhere.md", "elsewhere\n")
    (dst / "stray").symlink_to(target)

    _mirror_tree(live, dst)

    assert (dst / "a.md").read_text() == "a\n"
    assert (dst / "stray").is_symlink()
    assert target.read_text() == "elsewhere\n"


def test_bundle_reports_skipped_paths_once_per_export(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    knowledge = tmp_path / "knowledge"
    skills = tmp_path / "skills"
    _write(knowledge, "notes/a.md")
    (knowledge / "notes" / "link.md").symlink_to(_write(tmp_path, "outside.md"))
    _write(skills, "demo/SKILL.md")
    _write(skills, "demo/.git/HEAD")
    bundle = Bundle(tmp_path / "worktree", trees=[("knowledge", knowledge), ("skills", skills)])

    with caplog.at_level(logging.WARNING, logger="coffer.infrastructure.sync.bundle"):
        bundle.mirror_trees_out()

    warnings = [r for r in caplog.records if "skipped" in r.getMessage()]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "2 path(s)" in message
    assert "knowledge/notes/link.md" in message and "skills/demo/.git" in message
    assert not (tmp_path / "worktree" / "knowledge" / "notes" / "link.md").exists()
    assert not (tmp_path / "worktree" / "skills" / "demo" / ".git").exists()
