"""Integration: ripgrep wrapper over a docs directory."""

from __future__ import annotations

import shutil

import pytest

from coffer.infrastructure.knowledge.grep import RipgrepGrep

pytestmark = pytest.mark.skipif(shutil.which("rg") is None, reason="ripgrep not installed")


@pytest.mark.asyncio
async def test_grep_returns_file_line_matches(tmp_path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("first line\nmatch here\nthird line\n", encoding="utf-8")
    (docs / "b.md").write_text("nothing relevant\n", encoding="utf-8")

    hits = await RipgrepGrep().grep(str(docs), "match here")
    assert len(hits) == 1
    assert hits[0].line_number == 2
    assert "match here" in hits[0].line
    assert hits[0].path.endswith("a.md")


@pytest.mark.asyncio
async def test_grep_respects_max_matches(tmp_path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "many.md").write_text("\n".join("needle" for _ in range(50)), encoding="utf-8")
    hits = await RipgrepGrep().grep(str(docs), "needle", max_matches=5)
    assert len(hits) <= 5


@pytest.mark.asyncio
async def test_grep_missing_dir_returns_empty(tmp_path) -> None:
    hits = await RipgrepGrep().grep(str(tmp_path / "nope"), "x")
    assert hits == []
