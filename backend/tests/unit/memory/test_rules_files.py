"""Unit tests for infrastructure/memory/rules_files.py."""

from __future__ import annotations

import pathlib

from coffer.infrastructure.knowledge.paths import rule_file_path, rules_dir, rules_path
from coffer.infrastructure.memory.rules_files import (
    append_rule,
    count_rules,
    read_all_rules,
    read_rules,
    rule_bullets,
    write_rules_file,
)


def test_append_rule_creates_header_and_bullet(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    path = rules_path(store_dir)
    result = append_rule(path, "always run make verify before pushing")
    assert result is True
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Rules\n")
    assert "- always run make verify before pushing" in text


def test_append_rule_second_distinct_adds_bullet(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    path = rules_path(store_dir)
    append_rule(path, "rule one")
    result = append_rule(path, "rule two")
    assert result is True
    text = path.read_text(encoding="utf-8")
    assert "- rule one" in text
    assert "- rule two" in text


def test_append_rule_exact_duplicate_is_noop(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    path = rules_path(store_dir)
    append_rule(path, "never do this")
    before = path.read_text(encoding="utf-8")
    result = append_rule(path, "never do this")
    assert result is False
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_read_rules_returns_none_for_missing(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    assert read_rules(rules_path(store_dir)) is None


def test_read_rules_returns_text_when_present(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    path = rules_path(store_dir)
    append_rule(path, "some rule")
    text = read_rules(path)
    assert text is not None
    assert "some rule" in text


def test_rules_dir_resolves_under_store_root(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    d = rules_dir(store_dir)
    assert d == store_dir / "rules"


def test_rules_path_resolves_to_rules_md(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    p = rules_path(store_dir)
    assert p == store_dir / "rules" / "rules.md"


def test_rules_path_is_under_store_root(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    p = rules_path(store_dir)
    assert str(p).startswith(str(store_dir))


# --- multi-file rules: split-lane helpers (amendment 2026-06-22) ---


def test_rule_file_path_is_category_file(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    assert rule_file_path(store_dir, "git") == store_dir / "rules" / "git.md"


def test_rule_file_path_rejects_traversal(tmp_path: pathlib.Path) -> None:
    import pytest

    with pytest.raises(ValueError):
        rule_file_path(tmp_path / "store", "../escape")


def test_rule_bullets_extracts_rule_texts() -> None:
    text = "# Rules\n- first rule\n- second rule\n* third rule\n"
    assert rule_bullets(text) == ["first rule", "second rule", "third rule"]


def test_count_rules_counts_bullets_only() -> None:
    text = "# Rules\n- a\n- b\nnot a bullet\n- c\n"
    assert count_rules(text) == 3


def test_write_rules_file_writes_header_and_bullets(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "rules" / "git.md"
    write_rules_file(path, ["commit small", "branch off main"])
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Rules\n")
    assert rule_bullets(text) == ["commit small", "branch off main"]


def test_write_rules_file_dedupes_preserving_order(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "rules" / "git.md"
    write_rules_file(path, ["a", "b", "a", "c"])
    assert rule_bullets(path.read_text(encoding="utf-8")) == ["a", "b", "c"]


def test_read_all_rules_none_when_empty(tmp_path: pathlib.Path) -> None:
    assert read_all_rules(rules_dir(tmp_path / "store")) is None


def test_read_all_rules_reads_legacy_single_file(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    append_rule(rules_path(store_dir), "only rule")
    out = read_all_rules(rules_dir(store_dir))
    assert out is not None and "only rule" in out


def test_read_all_rules_concatenates_category_files(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    write_rules_file(rule_file_path(store_dir, "git"), ["commit small"])
    write_rules_file(rule_file_path(store_dir, "testing"), ["write tests first"])
    out = read_all_rules(rules_dir(store_dir))
    assert out is not None
    assert "commit small" in out
    assert "write tests first" in out
