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

    result = await RipgrepGrep().grep(str(docs), "match here")
    hits = result.hits
    assert len(hits) == 1
    assert hits[0].line_number == 2
    assert "match here" in hits[0].line
    assert hits[0].path.endswith("a.md")
    assert result.truncated is False


@pytest.mark.asyncio
async def test_grep_respects_max_matches(tmp_path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "many.md").write_text("\n".join("needle" for _ in range(50)), encoding="utf-8")
    result = await RipgrepGrep().grep(str(docs), "needle", max_matches=5)
    assert len(result.hits) <= 5


@pytest.mark.asyncio
async def test_grep_missing_dir_returns_empty(tmp_path) -> None:
    result = await RipgrepGrep().grep(str(tmp_path / "nope"), "x")
    assert result.hits == ()


@pytest.mark.asyncio
async def test_grep_flags_truncation_at_cap(tmp_path) -> None:
    """``truncated`` must reflect that more matches exist beyond the cap — not
    a count heuristic that misfires when exactly cap matches exist."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "many.md").write_text("\n".join("needle" for _ in range(50)), encoding="utf-8")
    result = await RipgrepGrep().grep(str(docs), "needle", max_matches=5)
    assert len(result.hits) == 5
    assert result.truncated is True


@pytest.mark.asyncio
async def test_grep_exactly_cap_matches_is_not_truncated(tmp_path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "five.md").write_text("\n".join("needle" for _ in range(5)), encoding="utf-8")
    result = await RipgrepGrep().grep(str(docs), "needle", max_matches=5)
    assert len(result.hits) == 5
    assert result.truncated is False


@pytest.mark.asyncio
async def test_grep_timeout_is_flagged_not_silent(tmp_path) -> None:
    """A timed-out grep must kill the subprocess and report ``truncated=True``
    rather than masquerading as 'no matches'."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("needle\n", encoding="utf-8")
    result = await RipgrepGrep(timeout_s=0.000001).grep(str(docs), "needle")
    assert result.hits == ()
    assert result.truncated is True
