"""The change preview's line diff: numbered rows, hunk headers, context."""

from __future__ import annotations

from coffer.application.provider.line_diff import line_diff


def test_a_new_file_is_all_additions_numbered_from_one() -> None:
    rows = line_diff(None, "a\nb\n")
    assert [r.kind for r in rows] == ["hunk", "add", "add"]
    assert [r.new_no for r in rows[1:]] == [1, 2]
    assert all(r.old_no is None for r in rows)


def test_a_change_keeps_three_lines_of_context_and_both_numberings() -> None:
    before = "\n".join(f"l{i}" for i in range(1, 11)) + "\n"
    after = before.replace("l5", "L5")
    rows = line_diff(before, after)
    kinds = [r.kind for r in rows]
    assert kinds == ["hunk"] + ["context"] * 3 + ["remove", "add"] + ["context"] * 3
    removed = next(r for r in rows if r.kind == "remove")
    added = next(r for r in rows if r.kind == "add")
    assert (removed.old_no, removed.text) == (5, "l5")
    assert (added.new_no, added.text) == (5, "L5")


def test_a_deleted_file_is_all_removals() -> None:
    rows = line_diff("x\ny\n", None)
    assert [r.kind for r in rows] == ["hunk", "remove", "remove"]


def test_identical_text_has_no_rows() -> None:
    assert line_diff("same\n", "same\n") == []
