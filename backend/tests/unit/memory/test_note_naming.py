"""How a new note is named and typed (spec memory "Distil each raw entry into a note
mechanically")."""

from __future__ import annotations

import pytest

from coffer.application.memory import note_naming as naming
from coffer.domain.memory.note import TYPE_FEEDBACK, TYPE_PROJECT, TYPE_USER


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Worktree development", "worktree-development"),
        ("  Mixed/Case_Title  ", "mixed-case-title"),
        ("!!!", "note"),
        ("", "note"),
        ("中文标题", "中文标题"),
    ],
)
def test_a_slug_is_readable_and_never_empty(title: str, expected: str) -> None:
    assert naming.unique_slug(title, set()) == expected


def test_a_slug_collides_with_nothing_the_partition_already_holds() -> None:
    taken = {"worktree-development", "worktree-development-2"}
    assert naming.unique_slug("Worktree development", taken) == "worktree-development-3"


def test_a_very_long_title_is_cut_to_a_usable_file_name() -> None:
    slug = naming.unique_slug("word " * 100, set())
    assert 0 < len(slug) <= 80
    assert not slug.endswith("-")


@pytest.mark.parametrize(
    ("candidates", "expected"),
    [
        ((TYPE_USER,), TYPE_USER),
        (("", TYPE_FEEDBACK), TYPE_FEEDBACK),
        (("invented", "also-invented"), TYPE_PROJECT),
        ((), TYPE_PROJECT),
    ],
)
def test_a_stray_type_never_travels_into_a_note(candidates: tuple[str, ...], expected: str) -> None:
    assert naming.note_type(*candidates) == expected
