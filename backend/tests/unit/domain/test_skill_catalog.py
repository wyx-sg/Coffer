"""Unit tests for the pure catalog search (FR-032)."""

from __future__ import annotations

from coffer.domain.skill.catalog import CatalogEntry, search_catalog


def _e(name: str, desc: str = "", publisher: str = "acme") -> CatalogEntry:
    return CatalogEntry(
        name=name,
        description=desc,
        git_url="https://example.test/repo",
        git_ref="main",
        git_subpath="",
        publisher=publisher,
    )


def test_empty_query_returns_all_sorted():
    entries = [_e("zeta"), _e("alpha"), _e("mid")]
    out = search_catalog(entries, None)
    assert [e.name for e in out] == ["alpha", "mid", "zeta"]


def test_blank_query_returns_all():
    entries = [_e("a"), _e("b")]
    assert len(search_catalog(entries, "   ")) == 2


def test_filter_by_name_case_insensitive():
    entries = [_e("PDF-tools"), _e("docx")]
    out = search_catalog(entries, "pdf")
    assert [e.name for e in out] == ["PDF-tools"]


def test_filter_by_description():
    entries = [_e("a", desc="edit spreadsheets"), _e("b", desc="edit docs")]
    out = search_catalog(entries, "spreadsheet")
    assert [e.name for e in out] == ["a"]


def test_filter_by_publisher():
    entries = [_e("a", publisher="anthropics"), _e("b", publisher="vercel")]
    out = search_catalog(entries, "vercel")
    assert [e.name for e in out] == ["b"]


def test_no_match_returns_empty():
    assert search_catalog([_e("a")], "zzz") == []
