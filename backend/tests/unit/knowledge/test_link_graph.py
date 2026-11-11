"""A collection read for its links: how ``[[slug]]`` and relative links
resolve, and which ones are broken (spec knowledge "Resolve links by slug or
relative path", "Check every link in a collection").

The knowledge root resolves from the fresh ``HOME`` every test gets
(``backend/tests/conftest.py``), never the developer's real vault.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from coffer.infrastructure.knowledge import catalogue, file_links, fs, link_graph, links, paths


@pytest.fixture
def shopee() -> pathlib.Path:
    fs.create_collection_dir("shopee")
    return paths.collection_dir("shopee")


def _write(path: pathlib.Path, front: dict | None = None, body: str = "") -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = f"---\n{yaml.safe_dump(front)}---\n\n" if front is not None else ""
    path.write_text(f"{head}{body}\n", encoding="utf-8")
    return path


def _read(relpath: str):  # type: ignore[no-untyped-def]
    return file_links.describe(fs.read_file(relpath))


def _found(collection: str = "shopee") -> list[tuple[str, str, str | None]]:
    return [(f.kind, f.path, f.target) for f in link_graph.build(collection).findings()]


@pytest.mark.acceptance(spec="knowledge", scenario="a page's links resolve by slug and alias")
def test_links_resolve_by_slug_and_alias_and_skip_code(shopee: pathlib.Path) -> None:
    _write(shopee / "pages" / "session-ownership.md", {"aliases": ["sessions"]})
    _write(shopee / "pages" / "cache-ttl.md")
    _write(shopee / "notes" / "cache-ttl.md")
    _write(shopee / "notes" / "near.md", None, "See [[cache-ttl]].")
    _write(
        shopee / "pages" / "overview.md",
        None,
        "See [[session-ownership]], [[sessions|the session service]], [[Cache-TTL]] "
        "and [[gone]].\n\n```\n[[also-gone]]\n```\n\nInline `[[still-gone]]` too.",
    )

    page = _read("shopee/pages/overview.md")

    assert [(link.target, link.path) for link in page.links] == [
        ("session-ownership", "shopee/pages/session-ownership.md"),
        ("sessions", "shopee/pages/session-ownership.md"),
        ("Cache-TTL", "shopee/pages/cache-ttl.md"),
        ("gone", None),
    ]
    [near] = _read("shopee/notes/near.md").links
    assert (near.path, near.ambiguous) == ("shopee/notes/cache-ttl.md", False)
    assert _found() == [("dead_link", "shopee/pages/overview.md", "gone")]


def test_a_slug_two_folders_share_is_ambiguous_from_a_third(shopee: pathlib.Path) -> None:
    _write(shopee / "a" / "design.md")
    _write(shopee / "b" / "design.md")
    _write(shopee / "c.md", None, "[[design]]")

    [link] = _read("shopee/c.md").links
    assert (link.path, link.ambiguous) == (None, True)
    assert _found() == [("ambiguous_link", "shopee/c.md", "design")]


def test_the_readme_is_no_link_target_but_its_links_are_checked(shopee: pathlib.Path) -> None:
    _write(shopee / "README.md", None, "# shopee\n\nSee [the start](index.md) and [[gone]].")
    _write(shopee / "other.md", None, "[[README]]")

    assert _found() == [
        ("dead_link", "shopee/README.md", "gone"),
        ("dead_link", "shopee/README.md", "index.md"),
        ("dead_link", "shopee/other.md", "README"),
    ]


@pytest.mark.acceptance(spec="knowledge", scenario="a root index's relative links are checked")
def test_a_root_index_navigates_by_relative_links(shopee: pathlib.Path) -> None:
    for slug in ("gateway", "bff", "event"):
        _write(shopee / "pages" / f"{slug}.md", None, "Back to the [index](../index.md#services).")
    _write(
        shopee / "index.md",
        None,
        '# Index\n\n- [Gateway](pages/gateway.md)\n- [BFF](<pages/bff.md> "bff")\n'
        "- [Event][e]\n- [Gone](pages/gone.md)\n- [Site](https://example.com/x.md)\n"
        "- `[code](pages/nothing.md)`\n\n[e]: ./pages/event.md\n",
    )

    assert _found() == [("dead_link", "shopee/index.md", "pages/gone.md")]
    by_target = {link.target: link for link in _read("shopee/index.md").links}
    assert by_target["pages/gateway.md"].path == "shopee/pages/gateway.md"
    assert by_target["pages/gateway.md"].kind == "path"
    assert by_target["pages/gone.md"].path is None


@pytest.mark.acceptance(
    spec="knowledge", scenario="a link into another collection is followed and checked"
)
def test_links_between_collections_and_out_of_the_root(shopee: pathlib.Path) -> None:
    fs.create_collection_dir("platform")
    _write(paths.collection_dir("platform") / "pages" / "kafka.md", {"title": "Kafka"}, "x")
    _write(
        shopee / "pages" / "event.md",
        None,
        "Uses [Kafka](../../platform/pages/kafka.md), not [Pulsar](../../platform/pages/pulsar.md);"
        " never [this](../../../../etc/passwd) and never [that](../../platform/.inbox/x.md).",
    )

    found = _found()

    assert ("dead_link", "shopee/pages/event.md", "../../platform/pages/pulsar.md") in found
    assert ("dead_link", "shopee/pages/event.md", "../../platform/.inbox/x.md") in found
    assert ("outside_link", "shopee/pages/event.md", "../../../../etc/passwd") in found
    assert not [f for f in found if f[2] == "../../platform/pages/kafka.md"]
    read = {link.target: link for link in _read("shopee/pages/event.md").links}
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
    spec="knowledge", scenario="a file with no frontmatter is titled by its heading or name"
)
def test_files_without_frontmatter_are_never_findings(shopee: pathlib.Path) -> None:
    _write(shopee / "notes" / "team.md", None, "# The team\n\nNo frontmatter at all.")
    _write(shopee / "glossary.md", None, "Plain text.")

    assert _found() == []
    level = {f.path: f for f in catalogue.walk_files(shopee)}
    assert (level["shopee/notes/team.md"].title, level["shopee/notes/team.md"].description) == (
        "The team",
        "",
    )
    assert level["shopee/glossary.md"].title == "glossary"


@pytest.mark.acceptance(spec="knowledge", scenario="links in uploaded material are not checked")
def test_links_in_the_uploads_folder_are_not_checked(shopee: pathlib.Path) -> None:
    _write(
        shopee / "sources" / "td-design.md",
        {"title": "TD design"},
        "Macro text [[TD-123 and a [link](missing.md).",
    )
    _write(shopee / "pages" / "design.md", None, "From [[td-design]].")

    assert _found() == []
    [link] = _read("shopee/pages/design.md").links
    assert link.path == "shopee/sources/td-design.md"


def test_a_declared_uploads_folder_is_the_one_left_unchecked(shopee: pathlib.Path) -> None:
    _write(shopee / "README.md", {"uploads": "raw"}, "# shopee")
    _write(shopee / "raw" / "a.md", None, "[[nothing]]")
    _write(shopee / "sources" / "b.md", None, "[[nothing]]")

    assert _found() == [("dead_link", "shopee/sources/b.md", "nothing")]


@pytest.mark.acceptance(spec="knowledge", scenario="a file named with any characters is readable")
def test_a_file_named_with_any_characters_is_read_and_linked(shopee: pathlib.Path) -> None:
    _write(shopee / "Login (v2) & SSO.md", None, "# Login")
    _write(shopee / "ログイン.md", None, "# ログイン")
    _write(
        shopee / "index.md",
        None,
        "- [Login](<Login (v2) & SSO.md>)\n- [ログイン](ログイン.md)\n- [[Login (v2) & SSO]]",
    )

    assert fs.read_file("shopee/Login (v2) & SSO.md").title == "Login"
    assert fs.read_file("shopee/ログイン.md").title == "ログイン"
    assert _found() == []
