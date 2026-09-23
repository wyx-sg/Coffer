"""A partition read as a file tree, which is what the surface claims it is.

"Present partitions as a table and a file tree" rests on the claim that a
partition *is* a folder of derived Markdown, so all four of its parts are
reachable — with ``.raw/`` flagged as the verbatim input rather than Coffer's
own writing, so a reader can tell the two apart without knowing which directory
means which.

Two things this file is careful about, because both would make the surface lie
about the partition at exactly the moment a pass is rewriting it: the
``.<name>.tmp`` files an atomic write leaves for a few milliseconds are never
listed and never readable, and a path that escapes the partition is refused
**before** anything is opened.

The HTTP shape of this (405 on a write, 400 on an escape) lives with the
route; this is the reader underneath it.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.memory.files import (
    MAX_FILE_BYTES,
    MemoryFileNotFound,
    build_tree,
    read_file,
)
from coffer.infrastructure.memory.paths import UnsafeMemoryPath


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


def test_the_tree_shows_all_four_parts_with_the_product_before_the_input(
    partition_dir: pathlib.Path,
) -> None:
    tree = build_tree(partition_dir)

    assert tree.path == ""
    assert tree.name == "coffer"
    assert _names(tree) == ["notes", ".raw", "MEMORY.md", "RETIRED.md"]


def test_only_the_hidden_directory_the_layer_owns_is_flagged_as_derived(
    partition_dir: pathlib.Path,
) -> None:
    children = {c.name: c for c in build_tree(partition_dir).children}
    assert children[".raw"].derived is True
    assert children["notes"].derived is False


def test_a_notes_file_carries_its_relative_path_and_size(partition_dir: pathlib.Path) -> None:
    notes = next(c for c in build_tree(partition_dir).children if c.name == "notes")
    (file,) = notes.children
    assert (file.path, file.type) == ("notes/worktree-trap.md", "file")
    assert file.size == len("---\ntitle: t\n---\nbody\n")
    assert notes.size is None


def test_a_half_written_temp_file_is_neither_listed_nor_readable(
    partition_dir: pathlib.Path,
) -> None:
    (partition_dir / ".MEMORY.md.tmp").write_text("half a file", encoding="utf-8")

    assert ".MEMORY.md.tmp" not in _names(build_tree(partition_dir))
    with pytest.raises(MemoryFileNotFound):
        read_file("coffer", partition_dir, ".MEMORY.md.tmp")


def test_a_partition_with_no_directory_yet_is_an_empty_root_not_an_error(
    tmp_path: pathlib.Path,
) -> None:
    tree = build_tree(tmp_path / "never-written")
    assert tree.children == []


def test_a_symlink_pointing_outside_the_partition_is_skipped(
    partition_dir: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    outside = tmp_path / "secrets.md"
    outside.write_text("not yours", encoding="utf-8")
    (partition_dir / "escape.md").symlink_to(outside)

    assert "escape.md" not in _names(build_tree(partition_dir))
    with pytest.raises(UnsafeMemoryPath):
        read_file("coffer", partition_dir, "escape.md")


@pytest.mark.parametrize(
    "relpath", ["MEMORY.md", "RETIRED.md", "notes/worktree-trap.md", ".raw/3f2a91c4de55b071.md"]
)
def test_every_part_of_the_partition_reads(partition_dir: pathlib.Path, relpath: str) -> None:
    content = read_file("coffer", partition_dir, relpath)
    assert content.path == relpath
    assert content.content
    assert content.binary is False
    assert content.truncated is False


@pytest.mark.parametrize("relpath", ["../outside.md", "notes/../../outside.md"])
def test_a_path_escaping_the_partition_is_refused_before_a_byte_is_read(
    partition_dir: pathlib.Path, relpath: str
) -> None:
    (partition_dir.parent / "outside.md").write_text("not yours", encoding="utf-8")
    with pytest.raises(UnsafeMemoryPath):
        read_file("coffer", partition_dir, relpath)


def test_reading_the_partition_directory_itself_is_not_found(partition_dir: pathlib.Path) -> None:
    with pytest.raises(MemoryFileNotFound) as caught:
        read_file("coffer", partition_dir, "")
    assert caught.value.partition == "coffer"
    assert caught.value.code == "MEMORY_FILE_NOT_FOUND"


def test_a_file_with_a_nul_byte_comes_back_flagged_rather_than_as_mojibake(
    partition_dir: pathlib.Path,
) -> None:
    (partition_dir / "notes" / "binary.md").write_bytes(b"pre\x00post")

    content = read_file("coffer", partition_dir, "notes/binary.md")

    assert content.binary is True
    assert content.content == ""
    assert content.size == 8


def test_a_file_past_the_cap_is_truncated_and_says_so(partition_dir: pathlib.Path) -> None:
    (partition_dir / "notes" / "huge.md").write_text("x" * (MAX_FILE_BYTES + 10), encoding="utf-8")

    content = read_file("coffer", partition_dir, "notes/huge.md")

    assert content.truncated is True
    assert len(content.content) == MAX_FILE_BYTES
    assert content.size == MAX_FILE_BYTES + 10
