"""Importing a Confluence page into a collection, end to end through the
upload service (spec knowledge "Import a Confluence page as a readable source
with its attachments" and "Fill frontmatter on converted material").
"""

from __future__ import annotations

import base64
import json

import pytest

from coffer.application.knowledge.ingest import REPORT_KEY, IngestService
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.errors import KnowledgeSourceExists
from coffer.infrastructure.knowledge import fs, paths
from coffer.infrastructure.knowledge.converters.registry import default_registry
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from tests.unit.knowledge.test_ingest import _Audit, _on_disk, _Resources


@pytest.fixture
def service(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    fs.create_collection_dir("shopee")
    knowledge = KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit())
    return IngestService(knowledge=knowledge, registry=default_registry())


def _export(version: int = 7, body: str | None = None) -> bytes:
    return json.dumps(
        {
            "kind": "confluence.page",
            "schemaVersion": 1,
            "pageId": "42",
            "title": "Account Core",
            "spaceKey": "SPACE",
            "bodyFormat": "storage",
            "body": body
            or (
                "<h1>Intro</h1><p>Account core owns logins.</p>"
                '<p><ac:image><ri:attachment ri:filename="a.png" /></ac:image></p>'
                '<p><ac:image><ri:attachment ri:filename="gone.png" /></ac:image></p>'
            ),
            "version": version,
            "pageUrl": "https://confluence.example/pages/viewpage.action?pageId=42",
            "attachments": [{"name": "a.png", "dataBase64": base64.b64encode(b"PNG").decode()}],
        }
    ).encode()


def _raw(relpath: str) -> str:
    return paths.resolve(relpath).read_text(encoding="utf-8")


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="a Confluence page is imported with its macros read and its pictures kept",
)
async def test_a_page_becomes_one_source_with_its_files_and_report(service) -> None:  # type: ignore[no-untyped-def]
    result = await service.ingest(
        collection="shopee", filename="page.json", data=_export(), actor="tester"
    )

    assert result.converter == "confluence"
    assert result.path == "shopee/sources/account-core.md"
    assert result.page_id == "42"
    text = _raw(result.path)
    # One frontmatter block, the page's own title, a description from its prose.
    assert text.count("\n---\n") == 1 and text.startswith("---\n")
    fm, body = split_frontmatter(text)
    assert fm["title"] == "Account Core"
    assert fm["description"] == "Account core owns logins."
    assert fm["origin"]["page_id"] == "42" and fm["origin"]["version"] == 7
    assert fm[REPORT_KEY]["complete"] is False
    assert fm[REPORT_KEY]["missing"] == ["gone.png: not downloaded with the page"]
    assert "![a.png](../assets/confluence-42-v7/a.png)" in body
    assert sorted(_on_disk()) == [
        "assets/confluence-42-v7/a.png",
        "assets/confluence-42-v7/storage.xml",
        "sources/account-core.md",
    ]
    assert result.report is not None and not result.report.complete


@pytest.mark.acceptance(
    spec="knowledge", scenario="a page already imported is replaced only when asked"
)
async def test_a_page_imported_again_is_refused_unless_replaced(service) -> None:  # type: ignore[no-untyped-def]
    first = await service.ingest(
        collection="shopee", filename="page.json", data=_export(), actor="tester"
    )

    with pytest.raises(KnowledgeSourceExists) as refused:
        await service.ingest(
            collection="shopee", filename="page.json", data=_export(8), actor="tester"
        )
    assert refused.value.source == first.path

    second = await service.ingest(
        collection="shopee", filename="page.json", data=_export(8), actor="tester", replace=True
    )

    assert second.replaces == (first.path,)
    assert second.path == "shopee/sources/account-core-2.md"
    older, _ = split_frontmatter(_raw(first.path))
    assert older["superseded_by"] == "account-core-2"
    # The older import's files are untouched; the newer one has its own folder.
    assert "assets/confluence-42-v7/a.png" in _on_disk()
    assert "assets/confluence-42-v8/a.png" in _on_disk()


async def test_the_same_version_imported_again_never_overwrites_its_files(service) -> None:  # type: ignore[no-untyped-def]
    await service.ingest(collection="shopee", filename="page.json", data=_export(), actor="t")
    again = await service.ingest(
        collection="shopee", filename="page.json", data=_export(), actor="t", replace=True
    )

    _, body = split_frontmatter(_raw(again.path))
    assert "../assets/confluence-42-v7-2/a.png" in body


@pytest.mark.acceptance(
    spec="knowledge", scenario="an import can be previewed without writing anything"
)
async def test_a_preview_writes_nothing(service) -> None:  # type: ignore[no-untyped-def]
    result = await service.ingest(
        collection="shopee", filename="page.json", data=_export(), actor="t", preview=True
    )

    assert result.preview
    assert result.path == "shopee/sources/account-core.md"
    assert "shopee/assets/confluence-42-v7/a.png" in result.files
    assert _on_disk() == []


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="an upload's own frontmatter becomes the source's, not a second block",
)
async def test_a_markdown_export_keeps_one_frontmatter_block(service) -> None:  # type: ignore[no-untyped-def]
    data = (
        b"---\n"
        b"title: Account Core\n"
        b"origin: https://confluence.example/pages/viewpage.action?pageId=42\n"
        b"retrieved_at: 2026-10-01\n"
        b"version: 7\n"
        b"redacted: none\n"
        b"---\n\n# Account Core\n\nAccount core owns logins.\n"
    )

    result = await service.ingest(
        collection="shopee", filename="account-core.md", data=data, actor="t"
    )

    text = _raw(result.path)
    fm, body = split_frontmatter(text)
    assert text.count("---\n") == 2
    assert fm["title"] == "Account Core"
    assert fm["description"] == "Account core owns logins."
    assert fm["version"] == 7 and fm["redacted"] == "none"
    assert not body.lstrip().startswith("---")
    # Its page id is read from its origin URL: the same page is not imported twice.
    with pytest.raises(KnowledgeSourceExists):
        await service.ingest(collection="shopee", filename="page.json", data=_export(), actor="t")
