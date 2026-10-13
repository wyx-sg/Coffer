"""Standard Markdown links, the files that are not pages, evidence and per-page
recheck intervals (spec knowledge "Link pages by slug and check every link",
"Check a collection mechanically on every read", "Ask for a recheck of a page
after the collection's interval").

The knowledge root resolves from the fresh ``HOME`` every test gets
(``backend/tests/conftest.py``), never the developer's real vault.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
import yaml

from coffer.infrastructure.knowledge import fs, paths, wiki, wiki_links, wiki_reads


@pytest.fixture
def shopee() -> pathlib.Path:
    fs.create_collection_dir("shopee")
    return paths.collection_dir("shopee")


def _write(
    directory: pathlib.Path, name: str, front: dict[str, object], body: str = ""
) -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    head = f"---\n{yaml.safe_dump(front)}---\n\n" if front else ""
    path.write_text(f"{head}{body}\n", encoding="utf-8")
    return path


def _page(root: pathlib.Path, slug: str, body: str = "", **front: object) -> pathlib.Path:
    fields: dict[str, object] = {
        "title": slug,
        "type": "concept",
        "description": "d",
        "sources": ["s"],
        "verified": dt.date.today().isoformat(),
    }
    fields.update(front)
    return _write(root / "pages", f"{slug}.md", fields, body)


def _found(collection: str = "shopee") -> set[tuple[str, str, str | None]]:
    return {(f.kind, f.path, f.target) for f in wiki.build(collection).findings()}


def _readme(front: str) -> None:
    paths.readme_path("shopee").write_text(f"---\n{front}\n---\n# shopee\n", encoding="utf-8")


# ----- standard links


@pytest.mark.acceptance(
    spec="knowledge", scenario="standard relative links are checked like wiki links"
)
def test_standard_relative_links_are_checked_like_wiki_links(shopee: pathlib.Path) -> None:
    _write(shopee / "sources", "s.md", {"title": "s"}, "text")
    _write(shopee / "assets" / "up-1", "pic.png", {}, "png")
    _page(shopee, "target")
    _page(
        shopee,
        "hub",
        'See [the target](target.md#usage), [spaced](<target.md> "title"), '
        "[gone](missing.md), ![pic](../assets/up-1/pic.png), ![lost](../assets/up-1/lost.png), "
        "[escape](../../../etc/passwd), [abs](/etc/hosts), "
        "[web](https://example.com/x.md), [mail](mailto:a@b.c), [anchor](#top), "
        "[encoded](%74arget.md?x=1).\n\n```\n[fenced](nowhere.md)\n```\n\n"
        "And `[inline](nowhere.md)`.",
        type="overview",
    )

    found = _found()

    assert ("dead_link", "shopee/pages/hub.md", "missing.md") in found
    assert ("dead_link", "shopee/pages/hub.md", "../assets/up-1/lost.png") in found
    assert ("outside_link", "shopee/pages/hub.md", "../../../etc/passwd") in found
    assert ("outside_link", "shopee/pages/hub.md", "/etc/hosts") in found
    hub_findings = {(k, t) for k, p, t in found if p == "shopee/pages/hub.md"}
    assert hub_findings == {
        ("dead_link", "missing.md"),
        ("dead_link", "../assets/up-1/lost.png"),
        ("outside_link", "../../../etc/passwd"),
        ("outside_link", "/etc/hosts"),
    }
    # The standard links reach `target`, so it is no orphan.
    assert not [f for f in found if f[0] == "orphan_page"]

    page = wiki_reads.describe(fs.read_file("shopee/pages/hub.md"))
    markdown = [(ln.target, ln.path, ln.outside) for ln in page.links if ln.kind == "markdown"]
    assert markdown == [
        ("target.md#usage", "shopee/pages/target.md", False),
        ("target.md", "shopee/pages/target.md", False),
        ("missing.md", None, False),
        ("../assets/up-1/pic.png", "shopee/assets/up-1/pic.png", False),
        ("../assets/up-1/lost.png", None, False),
        ("../../../etc/passwd", None, True),
        ("/etc/hosts", None, True),
        ("%74arget.md?x=1", "shopee/pages/target.md", False),
    ]


def test_a_cross_collection_link_is_checked_for_existence_only(shopee: pathlib.Path) -> None:
    fs.create_collection_dir("other")
    other = paths.collection_dir("other")
    _write(other / "sources", "s.md", {"title": "s"}, "text")
    _page(other, "lone")
    _page(other, "second", "[[lone]]")
    _write(shopee / "sources", "s.md", {"title": "s"}, "text")
    _page(shopee, "a", "[there](../../other/pages/lone.md) [gone](../../other/pages/gone.md)")

    found = _found()
    assert ("dead_link", "shopee/pages/a.md", "../../other/pages/gone.md") in found
    assert not [f for f in found if f[2] == "../../other/pages/lone.md"]
    # A link from another collection does not make `second` reachable there.
    assert ("orphan_page", "other/pages/second.md", None) in _found("other")


def test_a_symlink_out_of_the_root_is_an_outside_link(
    shopee: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    outside = tmp_path / "secret"
    outside.mkdir()
    (outside / "x.md").write_text("x", encoding="utf-8")
    (shopee / "escape").symlink_to(outside)
    _write(shopee / "sources", "s.md", {"title": "s"}, "text")
    _page(shopee, "a", "[x](../escape/x.md)")
    assert ("outside_link", "shopee/pages/a.md", "../escape/x.md") in _found()


def test_links_in_code_and_external_targets_are_not_links() -> None:
    body = (
        "[a](a.md) [b](http://x/b.md) [c](#c) [d](mailto:d@e.f) [e](coffer-asset:pic.png)\n"
        "```md\n[f](f.md)\n```\n~~~\n![g](g.png)\n~~~\n`[h](h.md)` "
        "[![i](i.png)](j.md) [k](k(1).md)"
    )
    assert wiki_links.markdown_links_in(body) == ("a.md", "i.png", "j.md", "k(1).md")


# ----- files that are not pages


@pytest.mark.acceptance(
    spec="knowledge", scenario="a root index makes the pages it links reachable"
)
def test_a_root_index_makes_the_pages_it_links_reachable(shopee: pathlib.Path) -> None:
    _write(shopee / "sources", "s.md", {"title": "s"}, "text")
    _page(shopee, "a")
    _page(shopee, "b")
    _page(shopee, "c")
    _page(shopee, "d")
    _write(shopee, "index.md", {}, "# Index\n\n- [A](pages/a.md)\n- [[b]]\n- [Dead](pages/zz.md)")
    _write(shopee, "log.md", {}, "## 2026-10-13\n\n[[nowhere]] [up](../../x.md)")
    _write(shopee, "schema.md", {}, "Types are free text.")
    _write(shopee / "notes", "mine.md", {}, "[c](../pages/c.md)")
    _write(shopee / "assets" / "up", "readme.md", {}, "[x](missing.md)")

    found = _found()

    orphans = {p for k, p, _ in found if k == "orphan_page"}
    assert orphans == {"shopee/pages/d.md"}
    assert ("dead_link", "shopee/index.md", "pages/zz.md") in found
    assert ("dead_link", "shopee/log.md", "nowhere") in found
    assert ("outside_link", "shopee/log.md", "../../x.md") in found
    # Nothing under assets/ is read, and no non-page file is checked as a page.
    assert not [f for f in found if f[1].startswith("shopee/assets/")]
    page_kinds = {"incomplete_page", "unsourced_page", "stale_page", "orphan_page"}
    holders = {p for k, p, _ in found if k in page_kinds}
    assert holders <= {f"shopee/pages/{s}.md" for s in "abcd"}


def test_a_source_s_links_count_but_are_never_findings(shopee: pathlib.Path) -> None:
    _write(
        shopee / "sources",
        "s.md",
        {"title": "s"},
        "[[x]] [gone](../pages/never.md) [out](../../../etc/passwd) [b](../pages/b.md)",
    )
    _page(shopee, "a", "[[s]]")
    _page(shopee, "b", "[[a]]")
    # `b` is reached only from the source.
    assert _found() == set()


def test_the_readme_links_count_and_are_checked(shopee: pathlib.Path) -> None:
    _write(shopee / "sources", "s.md", {"title": "s"}, "text")
    _page(shopee, "a")
    _page(shopee, "b", "[[a]]")
    paths.readme_path("shopee").write_text(
        "# shopee\n\nStart at [b](pages/b.md); see [old](pages/old.md).\n", encoding="utf-8"
    )
    found = _found()
    assert not [f for f in found if f[0] == "orphan_page"]
    assert ("dead_link", "shopee/README.md", "pages/old.md") in found


# ----- evidence and collection rules


@pytest.mark.acceptance(
    spec="knowledge", scenario="evidence and collection rules decide which pages need sources"
)
def test_evidence_and_collection_rules_decide_which_pages_need_sources(
    shopee: pathlib.Path,
) -> None:
    _page(shopee, "hub", "[[code]] [[howto]] [[bare]] [[one]]", type="overview", sources=[])
    _page(shopee, "code", sources=[], evidence=["code: coffer/backend/x.py@abc123"])
    _page(shopee, "one", sources=None, evidence="observed: the log says so")
    _page(shopee, "howto", type="How-To", sources=[])
    _page(shopee, "bare", sources=[])

    unsourced = {p for k, p, _ in _found() if k == "unsourced_page"}
    assert unsourced == {
        "shopee/pages/hub.md",
        "shopee/pages/howto.md",
        "shopee/pages/bare.md",
    }

    _readme("sourceless_types: [overview, how-to]")
    unsourced = {p for k, p, _ in _found() if k == "unsourced_page"}
    assert unsourced == {"shopee/pages/bare.md"}

    _readme("sourceless_types: overview, HOW-TO")
    unsourced = {p for k, p, _ in _found() if k == "unsourced_page"}
    assert unsourced == {"shopee/pages/bare.md"}


def test_page_types_are_free_text(shopee: pathlib.Path) -> None:
    _write(shopee / "sources", "s.md", {"title": "s"}, "text")
    _page(shopee, "hub", "[[cmp]] [[syn]] [[sum]]", type="comparison", subject_kind="service")
    _page(shopee, "cmp", "[[hub]]", type="synthesis")
    _page(shopee, "syn", "[[hub]]", type="summary", subject_kind="flow")
    _page(shopee, "sum", "[[hub]]", type="anything at all")
    assert wiki.build("shopee").findings() == []


# ----- rechecks


@pytest.mark.acceptance(spec="knowledge", scenario="a page sets its own recheck interval")
def test_a_page_sets_its_own_recheck_interval(shopee: pathlib.Path) -> None:
    _write(shopee / "sources", "s.md", {"title": "s"}, "text")
    _page(shopee, "hub", "[[fast]] [[off]] [[bad]] [[plain]]", type="overview")
    _page(shopee, "fast", verified="2026-10-01", verify_after_days=7)
    _page(shopee, "off", verified="2020-01-01", verify_after_days=0)
    _page(shopee, "bad", verified="2026-06-01", verify_after_days="soon")
    _page(shopee, "plain", verified="2026-09-01")
    _readme("verify_after_days: 60")
    today = dt.date(2026, 10, 13)

    stale = sorted(
        f.path for f in wiki.build("shopee", today=today).findings() if f.kind == wiki.STALE_PAGE
    )
    # `fast` outlived its own 7 days, `off` is never due, `bad` falls back to the
    # collection's 60 days, and `plain` is inside them.
    assert stale == ["shopee/pages/bad.md", "shopee/pages/fast.md"]


def test_a_null_verified_date_is_stale_and_nothing_writes_it(shopee: pathlib.Path) -> None:
    _write(shopee / "sources", "s.md", {"title": "s"}, "text")
    page = _page(shopee, "a", verified=None)
    before = page.read_bytes()

    graph = wiki.build("shopee")
    found = [(f.kind, f.target) for f in graph.findings()]
    read = wiki_reads.describe(fs.read_file("shopee/pages/a.md"))

    assert found == [("stale_page", None)]
    assert (read.stale, read.verified) == (True, "")
    assert page.read_bytes() == before
    assert "verified: null" in page.read_text(encoding="utf-8")
