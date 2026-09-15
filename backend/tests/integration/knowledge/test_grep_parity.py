"""The Python fallback and ripgrep answer a grep identically.

Run the same queries through both engines over one fixture tree and compare
the hit sets — the parity that lets a caller not care which one ran (spec
knowledge FR-022). Skipped where ``rg`` is not installed, because then there
is nothing to compare against.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest

from coffer.domain.errors import GrepPatternInvalid
from coffer.domain.knowledge.entry import GrepOutcome
from coffer.infrastructure.knowledge import grep as grep_module
from coffer.infrastructure.knowledge.grep import RipgrepSearch

pytestmark = pytest.mark.skipif(shutil.which("rg") is None, reason="ripgrep not installed")


@pytest.fixture
def roots(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> list[pathlib.Path]:
    knowledge = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(knowledge))
    shopee = knowledge / "shopee"
    personal = knowledge / "personal"
    (shopee / "account" / "deep").mkdir(parents=True)
    (shopee / ".history").mkdir()
    personal.mkdir()
    (shopee / "gateway.md").write_text(
        "---\ntitle: Gateway\n---\n\nThe gateway owns 登录态 tokens.\nSee account.session.\n"
        "Token: abc-123 and ABC-999\n",
        encoding="utf-8",
    )
    (shopee / "account" / "session.md").write_text(
        "登录态 lives in account.session\nplain line\nanother 登录态 mention\n",
        encoding="utf-8",
    )
    (shopee / "account" / "deep" / "notes.md").write_text(
        "line with token abc-777\n\nlast line no newline", encoding="utf-8"
    )
    (shopee / ".history" / "old.md").write_text("登录态 superseded\n", encoding="utf-8")
    (shopee / ".hidden.md").write_text("登录态 hidden\n", encoding="utf-8")
    (personal / "me.md").write_text("I prefer 登录态 handled by abc-000\n", encoding="utf-8")
    return [shopee, personal]


async def _both(roots: list[pathlib.Path], pattern: str, cap: int, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    with_rg = await RipgrepSearch().grep(roots, pattern, max_matches=cap)
    monkeypatch.setattr(grep_module.shutil, "which", lambda _name: None)
    without_rg = await RipgrepSearch().grep(roots, pattern, max_matches=cap)
    return with_rg, without_rg


def _key(outcome: GrepOutcome) -> list[tuple[str, int, str]]:
    return sorted((m.path, m.line_number, m.line) for m in outcome.matches)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pattern",
    ["登录态", r"abc-\d+", r"(?i)abc-9", r"^plain", r"account\.session", "nothing-here"],
)
async def test_both_engines_return_the_same_hits(
    roots: list[pathlib.Path], pattern: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_rg, without_rg = await _both(roots, pattern, 100, monkeypatch)
    assert _key(with_rg) == _key(without_rg)
    assert with_rg.truncated is without_rg.truncated
    if pattern == "登录态":
        # Sanity: the fixture has hits, and the hidden ones are not among them.
        assert len(with_rg.matches) == 4
        assert all(".history" not in m.path and ".hidden" not in m.path for m in with_rg.matches)


@pytest.mark.asyncio
async def test_both_engines_truncate_at_the_same_cap(
    roots: list[pathlib.Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    with_rg, without_rg = await _both(roots, "登录态", 2, monkeypatch)
    assert with_rg.truncated is True and without_rg.truncated is True
    assert len(with_rg.matches) == 2 and len(without_rg.matches) == 2


@pytest.mark.asyncio
async def test_both_engines_reject_an_invalid_pattern(
    roots: list[pathlib.Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(GrepPatternInvalid):
        await RipgrepSearch().grep(roots, "(unclosed", max_matches=10)
    monkeypatch.setattr(grep_module.shutil, "which", lambda _name: None)
    with pytest.raises(GrepPatternInvalid):
        await RipgrepSearch().grep(roots, "(unclosed", max_matches=10)
