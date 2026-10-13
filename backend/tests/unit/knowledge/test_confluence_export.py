"""A Confluence export the person fetched → a readable source (design §5).

Covers the accepted inputs (CLI read result JSON, REST JSON, ``*.storage.xml``),
the registry claiming them by content, the files kept, and the frontmatter
keys. The fixtures carry placeholder content only.
"""

from __future__ import annotations

import base64
import json
import pathlib
from datetime import UTC, datetime

import pytest

from coffer.domain.knowledge.converter import Conversion, UnsupportedDocument
from coffer.infrastructure.knowledge.converters.confluence import (
    ConfluenceConverter,
    convert_export,
    parse_export,
)
from coffer.infrastructure.knowledge.converters.registry import default_registry

FIXTURES = pathlib.Path(__file__).parents[2] / "fixtures" / "knowledge" / "confluence"
NOW = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
FORBIDDEN = ("<ac:", "<ri:", "skynet-confluence-storage", "CDATA", "<script", "<iframe")


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


async def _cli_page() -> Conversion:
    return await ConfluenceConverter(clock=lambda: NOW).convert(
        _fixture("page-cli.json"), "page.json"
    )


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="a Confluence page imports as a readable source with its pictures and diagrams",
)
async def test_cli_read_result_keeps_pictures_diagrams_and_the_storage() -> None:
    result = await _cli_page()

    assert result.converter == "confluence"
    assert result.title == "[Service] Service A Overview"
    assert result.asset_folder == "confluence-100200300-v7"
    assert result.keeps_original is True
    for needle in FORBIDDEN:
        assert needle not in result.markdown, needle
    files = {f.name: f.data for f in result.files}
    assert files["page.storage.xml"] == _fixture("page.storage.xml")
    attachments = {a["name"]: a for a in json.loads(_fixture("page-cli.json"))["attachments"]}
    picture = base64.b64decode(attachments["service a architecture.drawio.png"]["dataBase64"])
    assert files["service-a-architecture.drawio.png"] == picture
    assert (
        "![service a architecture.drawio.png](coffer-asset:service-a-architecture.drawio.png)"
        in (result.markdown)
    )
    assert {"diagram-1.drawio", "diagram-3.drawio", "diagram-4.puml", "request-flow.drawio"} <= set(
        files
    )
    assert "unused.png" not in files  # an attachment the body never shows is not kept
    assert "example-cli service enter service-a-<module>-<env>-xx" in result.markdown


async def test_cli_read_result_metadata_follows_the_design() -> None:
    meta = (await _cli_page()).metadata

    assert list(meta) == [
        "origin",
        "page_id",
        "page_version",
        "space",
        "retrieved_at",
        "representation",
        "original_representation",
        "redaction",
        "attachments",
        "import_status",
        "import_issues",
    ]
    assert meta["origin"] == "https://confluence.example.com/pages/viewpage.action?pageId=100200300"
    assert meta["page_id"] == "100200300"
    assert meta["page_version"] == 7
    assert meta["space"] == "EXA"
    assert meta["retrieved_at"] == "2026-10-13T10:00:00+00:00"
    assert meta["representation"] == "markdown from confluence storage"
    assert meta["original_representation"] == "coffer-asset:page.storage.xml"
    assert meta["redaction"] == "none"
    assert meta["import_status"] == "partial"
    for key in ("title", "description", "actor", "created_at", "updated_at"):
        assert key not in meta


@pytest.mark.acceptance(
    spec="knowledge", scenario="what an import could not keep is listed with its reason"
)
async def test_cli_read_result_lists_what_it_could_not_keep() -> None:
    result = await _cli_page()
    issues = {(i.kind, i.name): i.reason for i in result.issues}

    assert issues[("missing_attachment", "missing.png")] == "listed without its file"
    assert issues[("missing_attachment", "other.png")] == "on another page"
    assert issues[("external_image", "https://images.example.com/remote.png")]
    assert issues[("external_embed", "diagram-2")] == "hosted on Google Drive; not fetched"
    assert ("unsupported_macro", "mystery-widget") in issues
    assert ("unsupported_macro", "fancy-box") in issues
    assert ("not_rendered", "diagram-4.puml") in issues
    meta = result.metadata
    assert meta["import_issues"] == [
        {"kind": i.kind, "name": i.name, "reason": i.reason} for i in result.issues
    ]
    records = {r["name"]: r for r in meta["attachments"]}  # type: ignore[attr-defined]
    assert records["service-a-architecture.drawio.png"] == {
        "name": "service-a-architecture.drawio.png",
        "original_name": "service a architecture.drawio.png",
        "path": "coffer-asset:service-a-architecture.drawio.png",
        "status": "saved",
    }
    assert records["other.png"]["status"] == "missing"
    assert records["https://images.example.com/remote.png"]["status"] == "external"


def test_import_status_is_complete_when_only_not_rendered() -> None:
    storage = (
        '<ac:structured-macro ac:name="plantuml"><ac:plain-text-body><![CDATA[@startuml\n@enduml]]>'
        "</ac:plain-text-body></ac:structured-macro>"
    )
    data = json.dumps(
        {
            "kind": "confluence.page",
            "pageId": "5",
            "title": "T",
            "bodyFormat": "storage",
            "body": storage,
        }
    ).encode()
    inp = parse_export(data, "t.json")
    assert inp is not None
    result = convert_export(inp, now=NOW)
    assert [i.kind for i in result.issues] == ["not_rendered"]
    assert result.metadata["import_status"] == "complete"


async def test_rest_shape_is_read() -> None:
    inp = parse_export(_fixture("page-rest.json"), "content.json")
    assert inp is not None
    assert (inp.page_id, inp.version, inp.space, inp.title) == (
        "400500600",
        3,
        "EXB",
        "Service B Overview",
    )
    assert inp.origin == "https://confluence.example.com/display/EXB/Service+B+Overview"

    result = await default_registry().convert(_fixture("page-rest.json"), "content.json")
    assert result.converter == "confluence"
    assert result.asset_folder == "confluence-400500600-v3"
    assert '```python\nprint("<b>")\n```' in result.markdown
    assert "Service B handles **requests**." in result.markdown


async def test_storage_xml_file_is_read_without_metadata() -> None:
    data = _fixture("page.storage.xml")
    result = await default_registry().convert(data, "Service A.storage.xml")

    assert result.converter == "confluence"
    assert result.title == "Service A"
    assert (
        result.asset_folder.startswith("service-a-")
        and len(result.asset_folder) == len("service-a-") + 8
    )
    assert "page_id" not in result.metadata
    assert "# Basic Info" in result.markdown
    # No attachments travel with a bare Storage Format file.
    assert ("missing_attachment", "screenshot-1.png") in [(i.kind, i.name) for i in result.issues]


def test_redaction_and_retrieved_at_come_from_the_export_when_present() -> None:
    doc = json.loads(_fixture("page-rest.json"))
    doc["redacted"] = True
    doc["retrievedAt"] = "2026-10-01T00:00:00+00:00"
    inp = parse_export(json.dumps(doc).encode(), "c.json")
    assert inp is not None
    meta = convert_export(inp, now=NOW).metadata
    assert meta["redaction"] == "redacted"
    assert meta["retrieved_at"] == "2026-10-01T00:00:00+00:00"


async def test_cli_markdown_body_expands_its_markers() -> None:
    doc = {
        "kind": "confluence.page",
        "pageId": "8",
        "title": "Markdown Export",
        "bodyFormat": "markdown",
        "body": _fixture("page-markers.md").decode(),
        "version": 2,
    }
    result = await default_registry().convert(json.dumps(doc).encode(), "page.json")
    assert result.converter == "confluence"
    assert "skynet-confluence-storage" not in result.markdown
    assert "# Basic Info" in result.markdown
    assert result.files == ()
    assert result.metadata["representation"] == "markdown from a confluence markdown export"


@pytest.mark.parametrize(
    ("data", "filename"),
    [
        (b'{"name": "not a page"}', "settings.json"),
        (b"[1, 2]", "list.json"),
        (b"not json", "broken.json"),
        (b'<?xml version="1.0"?><project><name>x</name></project>', "pom.xml"),
        (b"<p>hello</p>", "page.md"),
    ],
)
def test_other_files_are_not_confluence(data: bytes, filename: str) -> None:
    assert parse_export(data, filename) is None
    assert ConfluenceConverter().sniff(data, filename) is False


async def test_a_json_that_is_not_a_page_still_passes_through() -> None:
    result = await default_registry().convert(b'{"a": 1}\n', "settings.json")
    assert result.converter == "passthrough"


async def test_an_xml_that_is_not_storage_stays_unsupported() -> None:
    with pytest.raises(UnsupportedDocument) as caught:
        await default_registry().convert(b'<?xml version="1.0"?><project/>', "pom.xml")
    assert caught.value.doc_type == "xml"


def test_confluence_converter_claims_nothing_by_extension_alone() -> None:
    converter = ConfluenceConverter()
    assert not converter.can_handle("xml")
    assert not converter.can_handle("json")


async def test_convert_refuses_what_it_cannot_read() -> None:
    with pytest.raises(UnsupportedDocument):
        await ConfluenceConverter().convert(b"{}", "x.json")


def test_kept_names_are_safe_and_unique() -> None:
    storage = "".join(
        f'<p><ac:image><ri:attachment ri:filename="{name}" /></ac:image></p>'
        for name in ("a b.png", "a?b.png", "page.storage.xml")
    )
    data = json.dumps(
        {
            "kind": "confluence.page",
            "pageId": "9",
            "title": "T",
            "bodyFormat": "storage",
            "body": storage,
            "attachments": [
                {"name": n, "dataBase64": base64.b64encode(n.encode()).decode()}
                for n in ("a b.png", "a?b.png", "page.storage.xml")
            ],
        }
    ).encode()
    inp = parse_export(data, "p.json")
    assert inp is not None
    names = [f.name for f in convert_export(inp, now=NOW).files]
    assert names == ["page.storage.xml", "a-b.png", "a-b-2.png", "page.storage-2.xml"]
