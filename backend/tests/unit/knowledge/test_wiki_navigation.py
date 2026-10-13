"""A collection's own files navigate it, and its check reads its own rules
(spec knowledge "Link pages by slug or relative path and check every link",
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

from coffer.infrastructure.knowledge import fs, links, paths, wiki, wiki_reads


@pytest.fixture
def shopee() -> pathlib.Path:
    fs.create_collection_dir("shopee")
    return paths.collection_dir("shopee")


def _write(path: pathlib.Path, front: dict | None, body: str = "") -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = f"---\n{yaml.safe_dump(front)}---\n\n" if front is not None else ""
    path.write_text(f"{head}{body}\n", encoding="utf-8")
    return path


def _page(root: pathlib.Path, slug: str, body: str = "", **front: object) -> pathlib.Path:
    fields = {
        "title": slug,
        "type": "entity",
        "description": "d",
        "sources": ["s"],
        "verified": dt.date.today().isoformat(),
    }
    fields.update(front)
    return _write(root / "pages" / f"{slug}.md", fields, body)


def _kinds(collection: str = "shopee") -> list[tuple[str, str, str | None]]:
    return [(f.kind, f.path, f.target) for f in wiki.build(collection).findings()]


@pytest.mark.acceptance(
    spec="knowledge", scenario="a root index's relative links make its pages reachable"
)
def test_a_root_index_navigates_by_relative_links(shopee: pathlib.Path) -> None:
    _write(shopee / "sources" / "s.md", {"title": "s"}, "text")
    _page(shopee, "gateway", "See [[core]].")
    _page(shopee, "core")
    _page(shopee, "bff")
    _page(shopee, "event", "Back to the [index](../index.md#services).")
    _write(
        shopee / "index.md",
        None,
        '# Index\n\n- [Gateway](pages/gateway.md)\n- [BFF](<pages/bff.md> "bff")\n'
        "- [Event][e]\n- [Gone](pages/gone.md)\n- [Site](https://example.com/x.md)\n"
        "- `[code](pages/nothing.md)`\n\n[e]: ./pages/event.md\n",
    )

    found = _kinds()

    assert ("orphan_page", "shopee/pages/gateway.md", None) not in found
    assert ("orphan_page", "shopee/pages/bff.md", None) not in found
    assert ("orphan_page", "shopee/pages/event.md", None) not in found
    assert ("orphan_page", "shopee/pages/core.md", None) not in found  # by [[core]]
    assert ("dead_link", "shopee/index.md", "pages/gone.md") in found
    # An external URL and a link in code are not file links.
    assert not [f for f in found if f[2] and ("example.com" in f[2] or "nothing" in f[2])]
    # The index is navigation: never asked for a type, sources or a recheck.
    assert not [f for f in found if f[1] == "shopee/index.md" and f[0] != "dead_link"]

    read = wiki_reads.describe(fs.read_file("shopee/index.md"))
    by_target = {link.target: link for link in read.links}
    assert by_target["pages/gateway.md"].path == "shopee/pages/gateway.md"
    assert by_target["pages/gateway.md"].kind == "path"
    assert by_target["pages/gone.md"].path is None


@pytest.mark.acceptance(
    spec="knowledge", scenario="a link into another collection is followed and checked"
)
def test_links_between_collections_and_out_of_the_root(shopee: pathlib.Path) -> None:
    fs.create_collection_dir("platform")
    _write(paths.collection_dir("platform") / "pages" / "kafka.md", {"title": "Kafka"}, "x")
    _write(shopee / "sources" / "s.md", {"title": "s"}, "text")
    _page(
        shopee,
        "event",
        "Uses [Kafka](../../platform/pages/kafka.md), not [Pulsar](../../platform/pages/pulsar.md);"
        " never [this](../../../../etc/passwd) and never [that](../../platform/.inbox/x.md).",
    )

    found = _kinds()

    assert ("dead_link", "shopee/pages/event.md", "../../platform/pages/pulsar.md") in found
    assert ("dead_link", "shopee/pages/event.md", "../../platform/.inbox/x.md") in found
    assert ("outside_link", "shopee/pages/event.md", "../../../../etc/passwd") in found
    assert not [f for f in found if f[2] == "../../platform/pages/kafka.md"]
    read = {
        link.target: link
        for link in wiki_reads.describe(fs.read_file("shopee/pages/event.md")).links
    }
    assert read["../../platform/pages/kafka.md"].path == "platform/pages/kafka.md"
    assert read["../../../../etc/passwd"].outside is True


def test_a_relative_link_resolves_inside_the_knowledge_root() -> None:
    assert links.resolve_path("shopee/pages/a.md", "../index.md") == "shopee/index.md"
    assert links.resolve_path("shopee/pages/a.md", "/assets/x.png") == "shopee/assets/x.png"
    assert links.resolve_path("shopee/pages/a.md", "../../other/b.md") == "other/b.md"
    assert links.resolve_path("shopee/pages/a.md", "../../../x.md") is None
    assert links.file_target("https://x.y/a.md") is None
    assert links.file_target("#top") is None
    assert links.file_target("pages/a%20b.md#part") == "pages/a b.md"


@pytest.mark.acceptance(
    spec="knowledge", scenario="a collection's own files are never asked for sources"
)
def test_root_files_and_custom_folders_are_not_pages(shopee: pathlib.Path) -> None:
    for name in ("index.md", "log.md", "schema.md", "notes/team.md"):
        _write(shopee / name, None, f"# {name}\n\nNo frontmatter at all.\n")
    _page(shopee, "only", sources=[])

    found = _kinds()

    assert [f[1] for f in found] == ["shopee/pages/only.md"]
    assert wiki.build("shopee").pages[0].path == "shopee/pages/only.md"


@pytest.mark.acceptance(
    spec="knowledge", scenario="a page names its evidence and the README its sourceless types"
)
def test_evidence_and_sourceless_types_answer_the_sources_check(shopee: pathlib.Path) -> None:
    _page(shopee, "overview-page", type="overview", sources=[])
    _page(shopee, "comparison-page", type="comparison", sources=[], body="[[overview-page]]")
    _page(
        shopee,
        "code-read",
        type="how-to",
        sources=[],
        evidence=["code: account-core/internal/session.go", "observed: 2026-10-12 on live"],
        body="[[overview-page]] [[comparison-page]]",
    )
    _page(shopee, "claims", type="synthesis", sources=[], body="[[code-read]]")

    unsourced = [f[1] for f in _kinds() if f[0] == "unsourced_page"]
    assert unsourced == ["shopee/pages/claims.md", "shopee/pages/comparison-page.md"]

    _write(
        shopee / "README.md",
        {"types_without_sources": ["overview", "comparison"]},
        "# shopee\n\nAbout.\n",
    )
    unsourced = [f[1] for f in _kinds() if f[0] == "unsourced_page"]
    assert unsourced == ["shopee/pages/claims.md"]
    # Any type a collection defines is a type: none is refused as unknown.
    assert not [f for f in _kinds() if f[0] == "incomplete_page"]


@pytest.mark.acceptance(
    spec="knowledge", scenario="a page's own interval overrides the collection's"
)
def test_a_page_sets_its_own_recheck_interval(shopee: pathlib.Path) -> None:
    today = dt.date(2026, 10, 13)
    _write(shopee / "sources" / "s.md", {"title": "s"}, "text")
    _page(shopee, "fast", verified="2026-09-01", verify_after_days=30)
    _page(shopee, "slow", verified="2026-01-01", review_after_days=365)
    _page(shopee, "off", verified="2020-01-01", verify_after_days=0)
    _page(shopee, "default", verified="2026-09-01")
    _page(shopee, "never", verified=None)

    graph = wiki.build("shopee", today=today)
    stale = {p.slug for p in graph.pages if graph.is_stale(p)}

    assert stale == {"fast", "never"}
    # A missing or null `verified` stays missing: nothing fills in a date.
    never = wiki_reads.describe(fs.read_file("shopee/pages/never.md"))
    assert (never.verified, never.stale) == ("", True)
    assert "verified: null" in (shopee / "pages" / "never.md").read_text(encoding="utf-8")


def test_review_after_days_is_read_as_the_collection_interval(shopee: pathlib.Path) -> None:
    _write(shopee / "README.md", {"review_after_days": 30}, "# shopee\n")
    assert wiki.verify_days("shopee") == 30
