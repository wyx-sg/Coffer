"""Unit tests for infrastructure/memory/rules_files.py."""

from __future__ import annotations

import pathlib

from coffer.infrastructure.knowledge.paths import rules_dir, rules_path
from coffer.infrastructure.memory.rules_files import append_rule, read_rules


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
