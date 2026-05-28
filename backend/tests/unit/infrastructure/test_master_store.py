"""MasterStore copy semantics — notably that `.git` is never copied in.

A git-sourced skill fetched with an empty subpath is the whole repository; an
unfiltered copytree would drag the entire `.git` directory into the canonical
store at ``~/.coffer/skills/<name>/``. Both ``copy_in`` and ``atomic_replace``
must filter it out.
"""

from __future__ import annotations

import pathlib

from coffer.infrastructure.skill.master_store import MasterStore


def _make_src_with_git(src: pathlib.Path) -> None:
    src.mkdir(parents=True, exist_ok=True)
    (src / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\nbody\n")
    git = src / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "config").write_text("[core]\n")


def test_copy_in_omits_dot_git(tmp_path):
    store = MasterStore(root=tmp_path / "store")
    src = tmp_path / "src"
    _make_src_with_git(src)

    paths = store.copy_in(src=src, name="my-skill")

    assert (paths.folder / "SKILL.md").is_file()
    assert not (paths.folder / ".git").exists()


def test_atomic_replace_omits_dot_git(tmp_path):
    store = MasterStore(root=tmp_path / "store")
    src1 = tmp_path / "src1"
    src1.mkdir()
    (src1 / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\nv1\n")
    store.copy_in(src=src1, name="my-skill")

    src2 = tmp_path / "src2"
    _make_src_with_git(src2)
    paths = store.atomic_replace(src=src2, name="my-skill")

    assert (paths.folder / "SKILL.md").read_text().endswith("body\n")
    assert not (paths.folder / ".git").exists()
