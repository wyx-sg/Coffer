"""Unit coverage for the read-only skill file viewer helpers.

The HTTP integration test (`test_skill_files.py`) drives these through the
import pipeline; these unit tests target the bounds directly: deep-recursion
safety in ``build_file_tree`` and memory-bounded reads in ``read_skill_file``.
"""

from __future__ import annotations

import pathlib

from coffer.application.skill.file_ops import (
    MAX_FILE_BYTES,
    MAX_TREE_DEPTH,
    build_file_tree,
    read_skill_file,
)


def test_deeply_nested_tree_does_not_raise(tmp_path):
    """A folder nested far past MAX_TREE_DEPTH returns instead of RecursionError."""
    root = tmp_path / "skill"
    deep = root
    # Go well beyond the bound to prove the depth guard, not Python's limit,
    # is what stops the walk.
    for i in range(MAX_TREE_DEPTH + 50):
        deep = deep / f"d{i}"
    deep.mkdir(parents=True)
    (deep / "leaf.txt").write_text("hi", encoding="utf-8")

    tree = build_file_tree(root)

    # Descend the tree and confirm exactly one branch is marked truncated and
    # the walk terminated cleanly.
    node = tree
    depth = 0
    truncated_seen = False
    while node.children:
        node = node.children[0]
        depth += 1
        if node.truncated:
            truncated_seen = True
            break
    assert truncated_seen
    assert depth <= MAX_TREE_DEPTH


def test_read_is_memory_bounded(tmp_path):
    """An oversize file is read at the cap (+1 probe) and flagged truncated."""
    root = tmp_path / "skill"
    root.mkdir()
    big = "a" * (MAX_FILE_BYTES + 5000)
    (root / "big.txt").write_text(big, encoding="utf-8")

    result = read_skill_file(root, "big.txt")

    assert result.truncated is True
    assert result.binary is False
    assert len(result.content) == MAX_FILE_BYTES
    # size reports the true on-disk length, not the bytes read.
    assert result.size == len(big)


def test_read_at_exact_cap_not_truncated(tmp_path):
    """A file exactly MAX_FILE_BYTES long is not flagged truncated."""
    root = tmp_path / "skill"
    root.mkdir()
    exact = "b" * MAX_FILE_BYTES
    (root / "exact.txt").write_text(exact, encoding="utf-8")

    result = read_skill_file(root, "exact.txt")

    assert result.truncated is False
    assert len(result.content) == MAX_FILE_BYTES


def test_read_rejects_path_escape(tmp_path):
    root = tmp_path / "skill"
    root.mkdir()
    (root / "SKILL.md").write_text("hi", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("nope", encoding="utf-8")

    try:
        read_skill_file(root, "../secret.txt")
    except ValueError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError("expected ValueError for path escape")
    assert isinstance(root, pathlib.Path)
