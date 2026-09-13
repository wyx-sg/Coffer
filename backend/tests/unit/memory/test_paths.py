"""The memory layer is a directory, so its path construction is unit-tested
the same way knowledge's is: no I/O, just "does this build the path the
contract promises, and does the guard refuse what it should."

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


def test_facts_dir_is_under_the_partition() -> None:
    assert paths.facts_dir("global") == paths.partition_dir("global") / "facts"


def test_fact_path_is_under_facts_dir_with_md_suffix() -> None:
    assert paths.fact_path("global", "worktree-development") == (
        paths.facts_dir("global") / "worktree-development.md"
    )


def test_summary_and_readme_paths_are_under_the_partition() -> None:
    assert paths.summary_path("coffer") == paths.partition_dir("coffer") / "summary.md"
    assert paths.readme_path("coffer") == paths.partition_dir("coffer") / "README.md"


def test_relative_of_strips_the_root() -> None:
    target = paths.fact_path("global", "a-fact")
    assert paths.relative_of(target) == str(pathlib.Path("global") / "facts" / "a-fact.md")


def test_relative_of_a_path_outside_the_root_returns_it_unchanged(
    tmp_path: pathlib.Path,
) -> None:
    outside = tmp_path.parent / "not-under-the-root"
    assert paths.relative_of(outside) == str(outside)


@pytest.mark.parametrize(
    "segment",
    ["", ".", "..", "...", ".hidden", "has/slash", "has\\backslash", "trailing.$"],
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


def test_fact_path_rejects_an_unsafe_slug() -> None:
    with pytest.raises(paths.UnsafeMemoryPath):
        paths.fact_path("global", "../escape")
