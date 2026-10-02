"""A partition listed as a file tree, which is what the surface claims it is.

"Cover memory management on REST and the CLI" rests on the claim that a
partition *is* a folder of derived Markdown, so Coffer's own writing (``MEMORY.md``,
``notes/``, ``RETIRED.md``) is listed, and the hidden ``.raw/`` of verbatim agent
input is not. The ``.<name>.tmp`` files an atomic write leaves for a few
milliseconds are never listed either, so the surface cannot show a half-written
file.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.memory.files import build_tree


@pytest.fixture
def partition_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "coffer"
    (root / "notes").mkdir(parents=True)
    (root / ".raw").mkdir()
    (root / "MEMORY.md").write_text("# coffer — Coffer memory\n", encoding="utf-8")
    (root / "RETIRED.md").write_text("# Retired\n", encoding="utf-8")
    (root / "notes" / "worktree-trap.md").write_text("---\ntitle: t\n---\nbody\n", encoding="utf-8")
    (root / ".raw" / "3f2a91c4de55b071.md").write_text("verbatim\n", encoding="utf-8")
    return root


def _names(node) -> list[str]:  # type: ignore[no-untyped-def]
    return [c.name for c in node.children]


def test_the_tree_shows_coffers_own_writing_and_not_the_raw_input(
    partition_dir: pathlib.Path,
) -> None:
    tree = build_tree(partition_dir)

    assert tree.path == ""
    assert tree.name == "coffer"
    assert _names(tree) == ["notes", "MEMORY.md", "RETIRED.md"]


def test_a_notes_file_carries_its_relative_path_and_size(partition_dir: pathlib.Path) -> None:
    notes = next(c for c in build_tree(partition_dir).children if c.name == "notes")
    (file,) = notes.children
    assert (file.path, file.type) == ("notes/worktree-trap.md", "file")
    assert file.size == len("---\ntitle: t\n---\nbody\n")
    assert notes.size is None


def test_a_partition_with_no_directory_yet_is_an_empty_root_not_an_error(
    tmp_path: pathlib.Path,
) -> None:
    tree = build_tree(tmp_path / "never-written")
    assert tree.children == []


def test_a_half_written_temp_file_is_not_listed(partition_dir: pathlib.Path) -> None:
    (partition_dir / ".MEMORY.md.tmp").write_text("half a file", encoding="utf-8")

    assert ".MEMORY.md.tmp" not in _names(build_tree(partition_dir))


def test_a_symlink_pointing_outside_the_partition_is_skipped(
    partition_dir: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    outside = tmp_path / "secrets.md"
    outside.write_text("not yours", encoding="utf-8")
    (partition_dir / "escape.md").symlink_to(outside)

    assert "escape.md" not in _names(build_tree(partition_dir))
