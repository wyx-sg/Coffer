"""MasterStore copy semantics — notably that `.git` is never copied in.

A git-sourced skill fetched with an empty subpath is the whole repository; an
unfiltered copytree would drag the entire `.git` directory into the canonical
store at ``~/.coffer/skills/<name>/``. Both ``copy_in`` and ``atomic_replace``
must filter it out.
"""

from __future__ import annotations

import pathlib

from coffer.infrastructure.skill.master_store import MasterStore, default_master_root
from coffer.infrastructure.sync.paths import skills_root


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


def test_default_master_root_honours_coffer_skills_root(monkeypatch):
    """``COFFER_SKILLS_ROOT`` moves the master store with the sync mirror.

    Before, it moved only the tree sync mirrors, so the round published a
    directory no skill was ever written to.
    """
    monkeypatch.setenv("HOME", "/home/someone")
    monkeypatch.setenv("COFFER_SKILLS_ROOT", "/elsewhere/skills")
    assert default_master_root() == pathlib.Path("/elsewhere/skills")
    assert default_master_root() == skills_root()


def test_default_master_root_falls_back_to_home(monkeypatch):
    monkeypatch.setenv("HOME", "/home/someone")
    monkeypatch.delenv("COFFER_SKILLS_ROOT", raising=False)
    assert default_master_root() == pathlib.Path("/home/someone/.coffer/skills")
    assert default_master_root() == skills_root()
