"""An upload keeps one frontmatter, its kept files land once, and a dry run
writes nothing (design "One frontmatter per upload", "Where things go",
"Upload report and re-import")."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.knowledge.ingest import IngestService
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.knowledge.converter import (
    Conversion,
    ConversionIssue,
    ConvertedFile,
)
from coffer.domain.knowledge.errors import KnowledgeFileNotFound
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import assets, fs, originals, paths
from coffer.infrastructure.knowledge.converters.passthrough_converter import (
    markdown_conversion,
    one_frontmatter,
)
from coffer.infrastructure.knowledge.converters.registry import default_registry
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter, with_key


class _Resources:
    def __init__(self) -> None:
        now = datetime.now(tz=UTC)
        self._row = Resource(
            uid="uid-1",
            kind=KIND_KNOWLEDGE,
            name="shopee",
            description=None,
            config={},
            enabled=True,
            created_at=now,
            updated_at=now,
            scope=None,
        )

    async def get(self, uid):  # type: ignore[no-untyped-def]
        return self._row

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return [self._row]


class _Audit:
    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        return None


class _Fixed:
    """A registry answering one conversion, whatever is uploaded."""

    def __init__(self, conversion: Conversion) -> None:
        self.conversion = conversion

    async def convert(self, data: bytes, filename: str) -> Conversion:
        return self.conversion


@pytest.fixture
def knowledge(tmp_path):  # type: ignore[no-untyped-def]
    fs.create_collection_dir("shopee")
    return KnowledgeService(resources=_Resources(), audit=_Audit())  # type: ignore[arg-type]


def _on_disk() -> list[str]:
    directory = paths.collection_dir("shopee")
    return sorted(str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file())


DOUBLE = b"""---
title: Outer title
description: '--- title: Inner title origin: https://wiki.example/x ---'
actor: agent
created_at: '2020-01-01T00:00:00+00:00'
summary: kept from the outer block
---

---
title: Inner title
origin: https://wiki.example/x
version: 3
actor: someone
---

# Heading in the body

The body's own opening prose.
"""


def test_two_blocks_become_one_and_the_inner_keys_win() -> None:
    metadata, body = one_frontmatter(DOUBLE.decode())
    assert metadata == {
        "title": "Inner title",
        "summary": "kept from the outer block",
        "origin": "https://wiki.example/x",
        "version": 3,
    }
    assert body.startswith("# Heading in the body")


def test_title_falls_back_to_the_first_heading_then_the_file_name() -> None:
    assert markdown_conversion("intro\n\n# Later\n", "a.md").title == "Later"
    assert markdown_conversion("no heading\n", "notes.md").title == "notes"
    assert markdown_conversion("---\ntitle: Given\n---\n# H\n", "a.md").title == "Given"


def test_a_yaml_file_is_not_split_as_frontmatter() -> None:
    import asyncio

    from coffer.infrastructure.knowledge.converters.passthrough_converter import (
        PassthroughConverter,
    )

    text = b"---\nkey: value\n---\nother: 1\n"
    conversion = asyncio.run(PassthroughConverter().convert(text, "conf.yaml"))
    assert conversion.markdown == text.decode()
    assert not conversion.metadata


@pytest.mark.acceptance(spec="knowledge", scenario="a Markdown upload keeps one frontmatter")
async def test_a_double_frontmatter_upload_is_kept_with_one(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = IngestService(knowledge=knowledge, registry=default_registry())
    result = await service.ingest(
        collection="shopee", filename="page.md", data=DOUBLE, actor="tester"
    )
    assert result.title == "Inner title"
    assert result.status == "complete" and result.issues == () and not result.dry_run
    text = paths.resolve(result.path).read_text(encoding="utf-8")
    assert text.count("\n---\n") == 1 and text.startswith("---\n")
    fm, body = split_frontmatter(text)
    assert fm["title"] == "Inner title"
    # Not the flattened block: the body's own opening prose.
    assert fm["description"] == "The body's own opening prose."
    assert (fm["origin"], fm["version"], fm["summary"]) == (
        "https://wiki.example/x",
        3,
        "kept from the outer block",
    )
    assert fm["actor"] == "user" and fm["created_at"] != "2020-01-01T00:00:00+00:00"
    assert list(fm)[:2] == ["title", "description"]
    assert "original" not in fm
    assert body.startswith("# Heading in the body")


async def test_a_plain_markdown_upload_takes_its_frontmatter_title(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = IngestService(knowledge=knowledge, registry=default_registry())
    data = b"---\ntitle: Runbook\ntags: [ops]\n---\n\nRestart the cache first.\n"
    result = await service.ingest(collection="shopee", filename="r.md", data=data, actor="t")
    fm, body = split_frontmatter(paths.resolve(result.path).read_text(encoding="utf-8"))
    assert result.path == "shopee/sources/runbook.md"
    assert (fm["title"], fm["description"], fm["tags"]) == (
        "Runbook",
        "Restart the cache first.",
        ["ops"],
    )
    assert body.strip() == "Restart the cache first."


def _import(name: str = "chart.png", data: bytes = b"png-1") -> Conversion:
    return Conversion(
        markdown="Prose.\n\n![chart](coffer-asset:chart.png)\n",
        title="Imported page",
        converter="confluence",
        files=(ConvertedFile(name, data), ConvertedFile("page.storage.xml", b"<p/>")),
        issues=(ConversionIssue("not_rendered", "diagram-1.puml", "plantuml"),),
        metadata={
            "representation": "markdown from confluence storage",
            "original_representation": "coffer-asset:page.storage.xml",
            "attachments": [{"name": name, "path": f"coffer-asset:{name}"}],
        },
        asset_folder="confluence-1-v2",
    )


async def test_kept_files_are_linked_in_the_body_and_the_frontmatter(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = IngestService(knowledge=knowledge, registry=_Fixed(_import()))
    result = await service.ingest(collection="shopee", filename="p.json", data=b"{}", actor="t")
    assert result.status == "complete"  # not_rendered does not make it partial
    assert result.files == (
        "shopee/assets/confluence-1-v2/chart.png",
        "shopee/assets/confluence-1-v2/page.storage.xml",
    )
    fm, body = split_frontmatter(paths.resolve(result.path).read_text(encoding="utf-8"))
    assert "![chart](../assets/confluence-1-v2/chart.png)" in body
    assert fm["original_representation"] == "../assets/confluence-1-v2/page.storage.xml"
    assert fm["attachments"][0]["path"] == "../assets/confluence-1-v2/chart.png"
    assert fm["retrieved_at"] and fm["original"] == "p.json"


async def test_the_same_files_reuse_their_folder_and_other_bytes_get_their_own(knowledge) -> None:  # type: ignore[no-untyped-def]
    first = IngestService(knowledge=knowledge, registry=_Fixed(_import()))
    await first.ingest(collection="shopee", filename="p.json", data=b"{}", actor="t")
    again = await first.ingest(collection="shopee", filename="p.json", data=b"{}", actor="t")
    assert again.files[0] == "shopee/assets/confluence-1-v2/chart.png"

    other = IngestService(knowledge=knowledge, registry=_Fixed(_import(data=b"png-2")))
    changed = await other.ingest(collection="shopee", filename="p.json", data=b"{x}", actor="t")
    sha8 = originals.digest(b"{x}")[:8]
    assert changed.files[0] == f"shopee/assets/confluence-1-v2-{sha8}/chart.png"
    assert paths.resolve("shopee/assets/confluence-1-v2/chart.png").read_bytes() == b"png-1"
    assert paths.resolve(changed.files[0]).read_bytes() == b"png-2"


def test_place_writes_nothing_new_for_identical_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    fs.create_collection_dir("shopee")
    assets.write_bytes("shopee/assets/f/a.png", b"a")
    folder, fresh = assets.place("shopee", "f", {"a.png": b"a", "b.png": b"b"}, "0" * 64)
    assert (folder, fresh) == ("f", {"shopee/assets/f/b.png": b"b"})


@pytest.mark.acceptance(
    spec="knowledge", scenario="a dry run previews an import and writes nothing"
)
async def test_a_dry_run_writes_nothing(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = IngestService(knowledge=knowledge, registry=_Fixed(_import()))
    before = _on_disk()
    result = await service.ingest(
        collection="shopee", filename="p.json", data=b"{}", actor="t", dry_run=True
    )
    assert result.dry_run and result.path == "shopee/sources/imported-page.md"
    assert result.files[0] == "shopee/assets/confluence-1-v2/chart.png"
    assert _on_disk() == before
    assert not originals.originals_dir().exists() or not any(originals.originals_dir().iterdir())


async def test_replaces_marks_the_old_source_superseded(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = IngestService(knowledge=knowledge, registry=default_registry())
    old = await service.ingest(
        collection="shopee", filename="v1.md", data=b"# Page\n\nv1 prose\n", actor="t"
    )
    new = await service.ingest(
        collection="shopee",
        filename="v2.md",
        data=b"# Page\n\nv2 prose\n",
        actor="t",
        replaces="sources/page.md",
    )
    assert new.replaced == old.path == "shopee/sources/page.md"
    fm, body = split_frontmatter(paths.resolve(old.path).read_text(encoding="utf-8"))
    assert fm["superseded_by"] == "page-2" and body.strip() == "# Page\n\nv1 prose"


async def test_replaces_must_name_a_source_of_the_collection(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = IngestService(knowledge=knowledge, registry=default_registry())
    with pytest.raises(KnowledgeFileNotFound):
        await service.ingest(
            collection="shopee", filename="a.md", data=b"x", actor="t", replaces="sources/no.md"
        )
    assert _on_disk() == []


def test_with_key_keeps_every_other_key_in_place() -> None:
    text = "---\nb: 1\na: two\n---\n\nBody\n"
    assert (
        with_key(text, "superseded_by", "x") == "---\nb: 1\na: two\nsuperseded_by: x\n---\n\nBody\n"
    )
