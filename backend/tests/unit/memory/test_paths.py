"""The memory layer is a directory, so its path construction is unit-tested
the same way knowledge's is: no I/O, just "does this build the path the
contract promises, and does the guard refuse what it should."

A partition holds four things with one writer each — ``MEMORY.md``, ``notes/``,
``RETIRED.md`` and the hidden ``.raw/`` — and ``paths.py`` is the sole owner of
every one of those names.

The root itself is already pinned to ``tmp_path`` by the suite-wide
``_isolated_memory_root`` fixture in ``backend/tests/conftest.py`` — every
test here runs against that, never a developer's real ``~/.coffer/memory``.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.memory import paths


def test_memory_root_honours_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    override = tmp_path / "somewhere-else"
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(override))
    assert paths.memory_root() == override


def test_memory_root_falls_back_to_home_when_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.delenv("COFFER_MEMORY_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.memory_root() == tmp_path / ".coffer" / "memory"


def test_partition_dir_is_one_segment_under_root() -> None:
    assert paths.partition_dir("global") == paths.memory_root() / "global"
    assert paths.partition_dir("coffer") == paths.memory_root() / "coffer"


def test_notes_live_in_their_own_directory_under_the_partition() -> None:
    assert paths.notes_dir("coffer") == paths.partition_dir("coffer") / "notes"
    assert paths.note_path("coffer", "worktree-development") == (
        paths.notes_dir("coffer") / "worktree-development.md"
    )


def test_raw_entries_live_in_the_partitions_hidden_directory() -> None:
    """``.raw/`` is the one hidden name the layer owns (see "Keep raw entries
    verbatim and hidden").

    ``check_segment`` refuses a dot-prefixed *caller-supplied* segment, so the
    only way this directory is reachable is through the constant — which is
    what keeps a note slug from ever addressing it.
    """
    assert paths.raw_dir("coffer") == paths.partition_dir("coffer") / ".raw"
    assert paths.raw_path("coffer", "3f2a91c4de55b071") == (
        paths.raw_dir("coffer") / "3f2a91c4de55b071.md"
    )


def test_index_and_retirement_record_sit_beside_the_notes_directory() -> None:
    assert paths.index_path("coffer") == paths.partition_dir("coffer") / "MEMORY.md"
    assert paths.retired_path("coffer") == paths.partition_dir("coffer") / "RETIRED.md"


def test_relative_of_strips_the_root() -> None:
    target = paths.note_path("global", "a-note")
    assert paths.relative_of(target) == str(pathlib.Path("global") / "notes" / "a-note.md")


def test_relative_of_a_path_outside_the_root_returns_it_unchanged(
    tmp_path: pathlib.Path,
) -> None:
    outside = tmp_path.parent / "not-under-the-root"
    assert paths.relative_of(outside) == str(outside)


@pytest.mark.parametrize(
    "segment",
    ["", ".", "..", "...", ".hidden", ".raw", "has/slash", "has\\backslash", "trailing.$"],
)
def test_check_segment_refuses_unsafe_names(segment: str) -> None:
    with pytest.raises(paths.UnsafeMemoryPath):
        paths.check_segment(segment)


@pytest.mark.parametrize("segment", ["global", "coffer", "my-project", "a.b_c", "项目"])
def test_check_segment_accepts_safe_names(segment: str) -> None:
    paths.check_segment(segment)  # does not raise


def test_partition_dir_rejects_an_unsafe_name() -> None:
    with pytest.raises(paths.UnsafeMemoryPath):
        paths.partition_dir("../escape")


def test_note_path_rejects_an_unsafe_slug() -> None:
    with pytest.raises(paths.UnsafeMemoryPath):
        paths.note_path("global", "../escape")


def test_raw_path_rejects_an_unsafe_entry_id() -> None:
    with pytest.raises(paths.UnsafeMemoryPath):
        paths.raw_path("global", "../escape")


def test_unsafe_path_error_carries_the_segment_and_the_reason() -> None:
    with pytest.raises(paths.UnsafeMemoryPath) as caught:
        paths.check_segment(".hidden")
    assert caught.value.segment == ".hidden"
    assert caught.value.reason
    assert caught.value.code == "MEMORY_UNSAFE_PATH"
