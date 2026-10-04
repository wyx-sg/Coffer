"""MasterStore copy semantics — notably that `.git` is never copied in.

A git-sourced skill fetched with an empty subpath is the whole repository; an
unfiltered copytree would drag the entire `.git` directory into the canonical
store at ``~/.coffer/vault/skills/<name>/``. Both ``copy_in`` and ``atomic_replace``
must filter it out.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.skill.master_store import MasterStore, default_master_root


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


def test_default_master_root_is_in_the_vault(monkeypatch):
    monkeypatch.setenv("HOME", "/home/someone")
    assert default_master_root() == pathlib.Path("/home/someone/.coffer/vault/skills")


def test_the_builtin_guide_s_folder_is_derived(tmp_path):
    """Coffer's own ``coffer-guide`` is rendered from the build: its folder is
    derived output, so it lives under ``derived/`` and never in the vault."""
    store = MasterStore(tmp_path / "vault" / "skills", derived=tmp_path / "derived" / "skills")
    assert (
        store.paths_for("coffer-guide").folder
        == (tmp_path / "derived" / "skills" / "coffer-guide").resolve()
    )
    assert (
        store.paths_for("my-skill").folder == (tmp_path / "vault" / "skills" / "my-skill").resolve()
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: coffer-guide\n---\nbody\n")
    written = store.copy_in(src=src, name="coffer-guide")
    assert (written.folder / "SKILL.md").is_file()
    store.atomic_replace(src=src, name="coffer-guide")
    assert store.exists("coffer-guide")
    assert not (tmp_path / "vault" / "skills" / "coffer-guide").exists()
    assert store.find_orphans(set()) == []


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a folder with an unsafe name does not stop delivery"
)
def test_a_folder_with_an_unsafe_name_is_not_an_orphan(tmp_path: pathlib.Path) -> None:
    """One stray folder must not break delivery for every skill: it is left out
    of the orphan list instead of raising when it is looked up."""
    store = MasterStore(tmp_path / "vault" / "skills", derived=tmp_path / "derived" / "skills")
    (tmp_path / "vault" / "skills" / "good-skill").mkdir(parents=True)
    (tmp_path / "vault" / "skills" / "my skill").mkdir()
    (tmp_path / "vault" / "skills" / "bad;name").mkdir()

    assert store.find_orphans(set()) == ["good-skill"]


def test_staging_a_copy_leaves_nothing_in_the_vault(tmp_path: pathlib.Path) -> None:
    store = MasterStore(tmp_path / "vault" / "skills", derived=tmp_path / "derived" / "skills")
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: s\n---\nbody\n")

    store.copy_in(src=src, name="s")
    store.atomic_replace(src=src, name="s")

    assert [p.name for p in (tmp_path / "vault" / "skills").iterdir()] == ["s"]
