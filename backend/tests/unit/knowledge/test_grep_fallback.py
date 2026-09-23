"""The pure-Python search stands in for ripgrep on a machine without it.

These pin the rules the fallback shares with ``rg``: hidden entries skipped,
binary files skipped, a regex applied line by line, a per-file and overall cap
one past the limit so truncation stays visible, and a timeout that reports
itself as truncation rather than as "no matches". Curation uses it to pick a
pass's candidate documents (spec knowledge "Assemble a pass from a bounded
context").
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from coffer.domain.errors import GrepPatternInvalid
from coffer.domain.knowledge.entry import GrepMatch
from coffer.infrastructure.knowledge import grep as grep_module
from coffer.infrastructure.knowledge.grep import RipgrepSearch
from coffer.infrastructure.knowledge.grep_fallback import grep_tree


@pytest.fixture
def root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    knowledge = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(knowledge))
    shopee = knowledge / "shopee"
    (shopee / "nested").mkdir(parents=True)
    (shopee / ".history").mkdir()
    (shopee / "a.md").write_text(
        "first 登录态 line\nsecond line\nthird 登录态 again\n", encoding="utf-8"
    )
    (shopee / "nested" / "b.md").write_text("登录态 nested\nno match here\n", encoding="utf-8")
    (shopee / ".history" / "old.md").write_text("登录态 in history\n", encoding="utf-8")
    (shopee / ".hidden.md").write_text("登录态 hidden file\n", encoding="utf-8")
    (shopee / "blob.bin").write_bytes(b"\x00\x01" + "登录态".encode() + b"\x00" * 60)
    return knowledge


def test_matches_every_visible_line_and_skips_hidden_and_binary(root: pathlib.Path) -> None:
    matches, timed_out = grep_tree([root / "shopee"], "登录态", 100, timeout_s=5.0)

    assert timed_out is False
    assert matches == [
        GrepMatch(path="shopee/a.md", line_number=1, line="first 登录态 line"),
        GrepMatch(path="shopee/a.md", line_number=3, line="third 登录态 again"),
        GrepMatch(path="shopee/nested/b.md", line_number=1, line="登录态 nested"),
    ]


def test_regex_semantics_apply_per_line(root: pathlib.Path) -> None:
    matches, _ = grep_tree([root / "shopee"], r"^(second|no) ", 100, timeout_s=5.0)
    assert [(m.path, m.line_number) for m in matches] == [
        ("shopee/a.md", 2),
        ("shopee/nested/b.md", 2),
    ]


def test_cap_applies_per_file_and_overall(root: pathlib.Path) -> None:
    matches, _ = grep_tree([root / "shopee"], "登录态", 1, timeout_s=5.0)
    assert len(matches) == 1

    matches, _ = grep_tree([root / "shopee"], "登录态", 2, timeout_s=5.0)
    assert [(m.path, m.line_number) for m in matches] == [
        ("shopee/a.md", 1),
        ("shopee/a.md", 3),
    ]


def test_invalid_regex_is_reported_as_a_pattern_error(root: pathlib.Path) -> None:
    with pytest.raises(GrepPatternInvalid):
        grep_tree([root / "shopee"], "(unclosed", 10, timeout_s=5.0)


def test_an_exhausted_budget_reports_a_timeout(root: pathlib.Path) -> None:
    matches, timed_out = grep_tree([root / "shopee"], "登录态", 100, timeout_s=-1.0)
    assert timed_out is True
    assert matches == []


@pytest.mark.asyncio
async def test_search_falls_back_when_rg_is_absent_and_logs_once(
    root: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(grep_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(grep_module, "_fallback_noted", False)

    with caplog.at_level(logging.INFO, logger="coffer.infrastructure.knowledge.grep"):
        first = await RipgrepSearch().grep([root / "shopee"], "登录态", max_matches=2)
        second = await RipgrepSearch().grep([root / "shopee"], "登录态", max_matches=10)

    assert first.truncated is True and len(first.matches) == 2
    assert second.truncated is False and len(second.matches) == 3
    notices = [r for r in caplog.records if r.message == "knowledge.grep.fallback"]
    assert len(notices) == 1


@pytest.mark.asyncio
async def test_fallback_timeout_is_truncation_not_silence(
    root: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(grep_module.shutil, "which", lambda _name: None)
    outcome = await RipgrepSearch(timeout_s=-1.0).grep([root / "shopee"], "登录态")
    assert outcome.truncated is True
    assert outcome.matches == ()
