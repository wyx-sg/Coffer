"""A collection read as a wiki: pages and sources, links by slug, which
sources wait, and the mechanical findings (spec knowledge "Link pages by slug
and check every link", "Derive which sources wait from the pages that cite
them", "Check a collection mechanically on every read").

The knowledge root resolves from the fresh ``HOME`` every test gets
(``backend/tests/conftest.py``), never the developer's real vault.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from coffer.infrastructure.knowledge import fs, paths, wiki


@pytest.fixture
def shopee() -> pathlib.Path:
    fs.create_collection_dir("shopee")
    return paths.collection_dir("shopee")


def _write(directory: pathlib.Path, name: str, front: dict, body: str = "") -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(f"---\n{yaml.safe_dump(front)}---\n\n{body}\n", encoding="utf-8")
    return path


def _page(shopee: pathlib.Path, slug: str, body: str = "", **front: object) -> pathlib.Path:
    fields = {"title": slug, "type": "concept", "description": "d", "sources": ["s"]}
    fields.update(front)
    return _write(shopee / "pages", f"{slug}.md", fields, body)


def _source(shopee: pathlib.Path, slug: str, **front: object) -> pathlib.Path:
    return _write(shopee / "sources", f"{slug}.md", {"title": slug, **front}, "text")


def _read(relpath: str):  # type: ignore[no-untyped-def]
    return wiki.describe(fs.read_file(relpath))


@pytest.mark.acceptance(spec="knowledge", scenario="a page's links resolve by slug and alias")
def test_links_resolve_by_slug_and_alias_and_skip_code(shopee: pathlib.Path) -> None:
    _source(shopee, "s")
    _page(shopee, "session-ownership", aliases=["sessions"])
    _page(shopee, "cache-ttl")
    _page(
        shopee,
        "overview",
        "See [[session-ownership]], [[sessions|the session service]], [[Cache-TTL]] "
        "and [[gone]].\n\n```\n[[also-gone]]\n```\n\nInline `[[still-gone]]` too.",
    )

    page = _read("shopee/pages/overview.md")

    assert page.kind == "page"
    assert [(link.target, link.path) for link in page.links] == [
        ("session-ownership", "shopee/pages/session-ownership.md"),
        ("sessions", "shopee/pages/session-ownership.md"),
        ("Cache-TTL", "shopee/pages/cache-ttl.md"),
        ("gone", None),
    ]
    findings = wiki.build("shopee").findings()
    dead = [(f.path, f.target) for f in findings if f.kind == wiki.DEAD_LINK]
    assert dead == [("shopee/pages/overview.md", "gone")]


def test_a_page_and_a_source_of_one_slug_resolve_to_the_page(shopee: pathlib.Path) -> None:
    _source(shopee, "s")
    _source(shopee, "design")
    _page(shopee, "design")
    _page(shopee, "index", "[[design]]")

    [link] = _read("shopee/pages/index.md").links
    assert (link.path, link.ambiguous) == ("shopee/pages/design.md", False)


def test_two_pages_of_one_alias_make_an_ambiguous_link(shopee: pathlib.Path) -> None:
    _source(shopee, "s")
    _page(shopee, "a", aliases=["shared"])
    _page(shopee, "b", aliases=["shared"])
    _page(shopee, "c", "[[shared]]")

    [link] = _read("shopee/pages/c.md").links
    assert (link.path, link.ambiguous) == (None, True)
    kinds = {f.kind for f in wiki.build("shopee").findings()}
    assert {wiki.AMBIGUOUS_LINK, wiki.DUPLICATE_SLUG} <= kinds


@pytest.mark.acceptance(
    spec="knowledge", scenario="a source waits until a page cites it or it is skipped"
)
def test_a_source_waits_until_cited_or_skipped(shopee: pathlib.Path) -> None:
    _source(shopee, "a")
    _source(shopee, "b")
    _source(shopee, "c", ingest="skipped")
    _page(shopee, "uses-a", sources=["a"])

    a = _read("shopee/sources/a.md")
    b = _read("shopee/sources/b.md")

    assert a.kind == "source"
    assert (a.waiting, [p.path for p in a.cited_by]) == (False, ["shopee/pages/uses-a.md"])
    assert (b.waiting, b.cited_by) == (True, ())
    graph = wiki.build("shopee")
    assert [s.path for s in graph.waiting()] == ["shopee/sources/b.md"]
    waiting = [f.path for f in graph.findings() if f.kind == wiki.WAITING_SOURCE]
    assert waiting == ["shopee/sources/b.md"]


def test_a_source_names_its_kept_original_only_beside_it(shopee: pathlib.Path) -> None:
    _source(shopee, "team", original="team.csv")
    (shopee / "sources" / "team.csv").write_text("a,b\n", encoding="utf-8")
    _source(shopee, "escape", original="../../secret.txt")

    assert _read("shopee/sources/team.md").original_path == str(shopee / "sources" / "team.csv")
    assert _read("shopee/sources/escape.md").original_path is None


def test_the_findings_name_every_mechanical_problem(shopee: pathlib.Path) -> None:
    _source(shopee, "s")
    _source(shopee, "waiting")
    _page(shopee, "linked", "[[nowhere]]", type="")  # incomplete, dead link
    _page(shopee, "orphan", "[[linked]]")
    _page(shopee, "map", "[[orphan]] [[linked]]", type="overview")  # exempt
    _page(shopee, "cites-gone", "[[map]]", sources=["missing"])
    _page(shopee, "bare", "[[map]]", sources=[])

    found = {(f.kind, f.path.split("/")[-1], f.target) for f in wiki.build("shopee").findings()}

    assert ("dead_link", "linked.md", "nowhere") in found
    assert ("incomplete_page", "linked.md", "type") in found
    assert ("missing_source", "cites-gone.md", "missing") in found
    assert ("unsourced_page", "bare.md", None) in found
    assert ("waiting_source", "waiting.md", None) in found
    orphans = {path for kind, path, _ in found if kind == "orphan_page"}
    assert orphans == {"cites-gone.md", "bare.md"}  # nobody links to them; map is an overview


def test_a_single_page_is_never_an_orphan(shopee: pathlib.Path) -> None:
    _source(shopee, "s")
    _page(shopee, "alone")
    assert wiki.build("shopee").findings() == []


def test_kind_follows_the_folder(shopee: pathlib.Path) -> None:
    assert paths.kind_of("shopee/pages/a.md") == "page"
    assert paths.kind_of("shopee/pages/deep/a.md") == "page"
    assert paths.kind_of("shopee/sources/a.md") == "source"
    assert paths.kind_of("shopee/sources/a.pdf") == "file"
    assert paths.kind_of("shopee/a.md") == "file"
    assert paths.kind_of("shopee/pages") == "file"
