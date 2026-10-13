"""A Confluence page's storage, read as the page a person sees (spec knowledge
"Import a Confluence page as a readable source with its attachments").

The fixtures are synthetic, shaped after real exports: a page wrapped whole in
``numberedheadings``, a ``code`` macro inside a table cell holding ``<module>``,
an ``info`` panel and an ``expand``, pictures downloaded and not, and the three
ways a draw.io diagram reaches a page.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
import zlib

import pytest

from coffer.domain.knowledge.converter import (
    BODY_CONVERTED,
    ITEM_CONVERTED,
    ITEM_DROPPED,
    ITEM_KEPT,
    ITEM_MISSING,
    ITEM_SKIPPED,
    ITEM_UNSUPPORTED,
)
from coffer.infrastructure.knowledge.converters.confluence import diagrams, markers, page, storage
from coffer.infrastructure.knowledge.converters.confluence.context import Context, safe_name
from coffer.infrastructure.knowledge.converters.passthrough_converter import PassthroughConverter
from coffer.infrastructure.knowledge.converters.registry import default_registry

_SCENARIO = "a Confluence page is imported with its macros read and its pictures kept"
_MXFILE = '<mxfile><diagram name="p">xyz</diagram></mxfile>'


def _macro(name: str, body: str = "", **params: str) -> str:
    p = "".join(f'<ac:parameter ac:name="{k}">{v}</ac:parameter>' for k, v in params.items())
    return (
        f'<ac:structured-macro ac:name="{name}" ac:schema-version="1" ac:macro-id="m">'
        f"{p}{body}</ac:structured-macro>"
    )


def _rich(body: str) -> str:
    return f"<ac:rich-text-body>{body}</ac:rich-text-body>"


def _code(text: str, language: str = "bash") -> str:
    return _macro(
        "code", f"<ac:plain-text-body><![CDATA[{text}]]></ac:plain-text-body>", language=language
    )


def _picture(name: str) -> str:
    return f'<p><ac:image ac:width="860"><ri:attachment ri:filename="{name}" /></ac:image></p>'


def _convert(xml: str, **attachments: bytes) -> tuple[str, Context]:
    ctx = Context(folder="confluence-1-v2", attachments=dict(attachments))
    return storage.convert(xml, ctx), ctx


# ----- rich text inside macros is the page's text ------------------------


@pytest.mark.acceptance(spec="knowledge", scenario=_SCENARIO)
def test_a_page_wrapped_in_numbered_headings_keeps_every_heading_and_table() -> None:
    xml = _macro("easy-heading-free") + _macro(
        "numberedheadings",
        _rich(
            "<h1>Basic Info</h1>"
            "<table><tbody><tr><th>Name</th><th>Owner</th></tr>"
            "<tr><td>account</td><td>team | a</td></tr></tbody></table>"
            "<h2>Run</h2><p>Start it.</p>"
        ),
    )
    md, ctx = _convert(xml)

    assert "# Basic Info" in md
    assert "## Run" in md
    assert "Start it." in md
    # A pipe in a cell is escaped, so the Markdown table keeps its columns.
    assert "| account | team \\| a |" in md
    assert "<!--" not in md and "ac:" not in md
    statuses = {i.name: i.status for i in ctx.macro_items}
    assert statuses["easy-heading-free"] == ITEM_DROPPED


@pytest.mark.acceptance(spec="knowledge", scenario=_SCENARIO)
def test_code_in_a_table_cell_keeps_its_text_and_language() -> None:
    xml = (
        "<table><tbody><tr><th>Step</th><th>Command</th></tr><tr><td>enter</td><td>"
        + _code("smc enter account-<module>-<env>-sg\ntail -f log/data.log")
        + "</td></tr></tbody></table>"
    )
    md, _ = _convert(xml)

    # A table holding code stays a small HTML table; the code is still code,
    # and ``<module>`` is text, never a tag.
    assert '<code class="language-bash">smc enter account-&lt;module&gt;-&lt;env&gt;-sg' in md
    assert "tail -f log/data.log" in md


def test_code_on_its_own_is_a_fenced_block_with_its_language() -> None:
    md, _ = _convert(_code("SELECT * FROM t WHERE a < 1;", language="sql"))

    assert "```sql\nSELECT * FROM t WHERE a < 1;\n```" in md


def test_panels_and_expands_show_their_content_and_the_toc_is_dropped() -> None:
    xml = (
        "<p>"
        + _macro("toc")
        + "</p>"
        + _macro("info", _rich("<p>Note this:</p><ul><li>a</li></ul>"))
        + _macro("expand", _rich("<p>Hidden detail</p>"), title="More")
    )
    md, ctx = _convert(xml)

    assert "> **Info**" in md and "> Note this:" in md
    assert "**More**" in md and "Hidden detail" in md
    assert any(i.name == "toc" and i.status == ITEM_DROPPED for i in ctx.macro_items)


def test_a_header_column_table_stays_html_with_its_links() -> None:
    xml = (
        '<table class="wrapped"><colgroup><col /></colgroup><tbody>'
        '<tr><th>CMDB</th><td><a href="https://cmdb.example/x">CMDB link</a></td></tr>'
        "</tbody></table>"
    )
    md, _ = _convert(xml)

    assert '<a href="https://cmdb.example/x">CMDB link</a>' in md
    assert "class=" not in md and "colgroup" not in md


def test_an_unknown_macro_keeps_its_text_or_is_reported_unsupported() -> None:
    md, ctx = _convert(_macro("someone-elses-macro", _rich("<p>Visible words</p>")))

    assert "Visible words" in md
    item = next(i for i in ctx.macro_items if i.name == "someone-elses-macro")
    assert "unknown macro" in item.reason

    md, ctx = _convert(_macro("chart-of-nothing"))
    assert "[Confluence macro chart-of-nothing: not supported]" in md
    assert ctx.macro_items[0].status == ITEM_UNSUPPORTED and ctx.partial


# ----- pictures, attachments and diagrams ----------------------------------


@pytest.mark.acceptance(spec="knowledge", scenario=_SCENARIO)
def test_a_downloaded_picture_is_kept_and_linked_relatively() -> None:
    md, ctx = _convert(_picture("arch diagram.png"), **{"arch diagram.png": b"PNG"})

    assert "![arch diagram.png](../assets/confluence-1-v2/arch-diagram.png)" in md
    assert [f.name for f in ctx.files] == ["arch-diagram.png"]
    assert ctx.attachment_items[0].status == ITEM_KEPT


@pytest.mark.acceptance(
    spec="knowledge", scenario="an attachment or embed that could not be kept is reported"
)
def test_pictures_that_could_not_be_kept_are_reported_and_marked() -> None:
    xml = (
        _picture("missing.png") + '<p><ac:image><ri:attachment ri:filename="theirs.png">'
        '<ri:page ri:content-title="Other Page" /></ri:attachment></ac:image></p>'
        + _macro(
            "html",
            '<ac:plain-text-body><![CDATA[<iframe src="https://viewer.diagrams.net/'
            '?highlight=0000ff#G1AbCdEf"></iframe>]]></ac:plain-text-body>',
        )
    )
    md, ctx = _convert(xml)

    assert "*[Picture not archived: missing.png]*" in md
    assert "<iframe" not in md
    reasons = {i.name: (i.status, i.reason) for i in ctx.attachment_items}
    assert reasons["missing.png"][0] == ITEM_MISSING
    assert reasons["theirs.png"] == (ITEM_MISSING, "an attachment of the page 'Other Page'")
    embed = next(i for i in ctx.macro_items if i.name == "html")
    assert embed.status == ITEM_MISSING and "Google Drive" in embed.reason


@pytest.mark.acceptance(
    spec="knowledge", scenario="a diagram shows as its picture, its link or its source"
)
def test_draw_io_diagrams_show_as_their_picture_or_a_link() -> None:
    link = "https://viewer.diagrams.net/?lightbox=1#R" + urllib.parse.quote(_MXFILE)
    inline = json.dumps({"xml": _MXFILE})
    xml = (
        _macro("drawio", diagramName="flow")
        + f'<p><a href="{link.replace("&", "&amp;")}">{link.replace("&", "&amp;")}</a></p>'
        + _macro(
            "html",
            f"<ac:plain-text-body><![CDATA[<div class=\"mxgraph\" data-mxgraph='{inline}'></div>"
            '<script src="https://viewer.diagrams.net/js/viewer-static.min.js"></script>'
            "]]></ac:plain-text-body>",
        )
    )
    md, ctx = _convert(xml, **{"flow.png": b"png", "flow": b"<mxfile/>"})

    # An attached diagram shows its picture; its source is not taken along.
    assert "![flow](../assets/confluence-1-v2/flow.png)" in md
    assert [f.name for f in ctx.files] == ["flow.png"]
    # The page's link stays the link it was, read as what it is.
    assert f"[draw.io diagram]({link})" in md
    # A diagram drawn in the page is a link that opens it, the diagram in its fragment.
    made = re.findall(r"\[draw\.io diagram\]\((https://viewer\.diagrams\.net/[^)\s]+)\)", md)
    assert len(made) == 2 and made[1].startswith(diagrams.VIEWER)
    packed = base64.b64decode(urllib.parse.unquote(made[1][len(diagrams.VIEWER) :]))
    assert urllib.parse.unquote(zlib.decompress(packed, -15).decode()) == _MXFILE
    assert "<script" not in md and "viewer-static" not in md


@pytest.mark.acceptance(
    spec="knowledge", scenario="a diagram shows as its picture, its link or its source"
)
def test_a_plantuml_macro_shows_its_source() -> None:
    xml = _macro(
        "plantuml",
        "<ac:plain-text-body><![CDATA[@startuml\nA -> B\n@enduml]]></ac:plain-text-body>",
    )
    md, ctx = _convert(xml)

    assert ctx.files == []
    assert "```plantuml\n@startuml\nA -> B\n@enduml\n```" in md
    assert ctx.macro_items[0].status == ITEM_CONVERTED


def test_names_are_made_safe_and_never_collide() -> None:
    ctx = Context(folder="f", attachments={"a b.png": b"1", "a-b.png": b"2"})

    first = ctx.attachment("a b.png", reason_missing="")
    second = ctx.attachment("a-b.png", reason_missing="")

    assert first == "../assets/f/a-b.png"
    assert second == "../assets/f/a-b-2.png"
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name(".hidden") == "hidden"


# ----- a whole page export --------------------------------------------------


def _export(**overrides: object) -> bytes:
    doc: dict[str, object] = {
        "id": "confluence:page:42",
        "schemaVersion": 1,
        "kind": "confluence.page",
        "pageId": "42",
        "title": "Account Core",
        "spaceKey": "SPACE",
        "status": "current",
        "bodyFormat": "storage",
        "body": "<h1>Intro</h1>" + _picture("a.png"),
        "version": 7,
        "pageUrl": "https://confluence.example/pages/viewpage.action?pageId=42",
        "attachments": [
            {"name": "a.png", "dataBase64": base64.b64encode(b"PNG").decode()},
            {"name": "unused.pdf"},
        ],
        "warnings": [],
    }
    doc.update(overrides)
    return json.dumps(doc).encode()


@pytest.mark.acceptance(spec="knowledge", scenario=_SCENARIO)
def test_a_page_export_converts_with_its_origin_raw_storage_and_report() -> None:
    found = page.read(_export())
    assert found is not None
    conversion = page.convert(found, fetched_at="2026-10-13T00:00:00+00:00")

    assert conversion.title == "Account Core"
    assert conversion.markdown.startswith("# Account Core\n\n# Intro")
    assert conversion.asset_folder == "confluence-42-v7"
    origin = conversion.metadata["origin"]
    assert origin["page_id"] == "42" and origin["version"] == 7
    assert origin["url"].endswith("pageId=42")
    assert "raw" not in origin
    names = {f.name for f in conversion.files}
    assert names == {"a.png"}
    report = conversion.report
    assert report is not None and report.body == BODY_CONVERTED
    assert {i.name: i.status for i in report.attachments} == {
        "a.png": ITEM_KEPT,
        "unused.pdf": ITEM_SKIPPED,
    }
    assert report.complete


def test_rest_answers_are_read_and_other_json_is_not_a_page() -> None:
    rest = {
        "id": "9",
        "type": "page",
        "title": "T",
        "version": {"number": 3},
        "space": {"key": "S"},
        "body": {"storage": {"value": "<p>x</p>"}},
        "_links": {"base": "https://c.example", "webui": "/pages/9"},
    }
    found = page.read(json.dumps(rest).encode())
    assert found is not None and found.version == 3 and found.url == "https://c.example/pages/9"
    assert page.read(b'{"name": "config"}') is None
    assert page.read(b"not json") is None


async def test_the_registry_claims_a_page_export_by_content() -> None:
    registry = default_registry()

    assert (await registry.convert(_export(), "page.json")).converter == "confluence"
    assert (await registry.convert(b'{"a": 1}', "settings.json")).converter == "passthrough"


# ----- a Markdown export -----------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="a Markdown export's storage markers are made readable"
)
def test_storage_markers_are_expanded_where_they_stand() -> None:
    inner = _macro("numberedheadings", _rich("<h1>Hidden Heading</h1><p>Body text</p>"))
    text = (
        "Before\n\n"
        f"<!-- skynet-confluence-storage:v1 kind=structured-macro\n{inner}\n-->\n\n"
        "<!-- a person's own comment -->\nAfter\n"
    )
    ctx = Context(folder="f")
    out = markers.expand(text, ctx)

    assert "# Hidden Heading" in out.markdown and "Body text" in out.markdown
    assert "skynet-confluence-storage" not in out.markdown
    assert "<!-- a person's own comment -->" in out.markdown
    assert out.storage == (inner,)


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="an upload's own frontmatter becomes the source's, not a second block",
)
async def test_markdown_frontmatter_is_read_not_passed_on() -> None:
    text = (
        "---\ntitle: Original Title\norigin: https://c.example/pages/viewpage.action?pageId=5\n"
        "version: 4\n---\n\n# Original Title\n\n"
        "<!-- skynet-confluence-storage:v1 kind=structured-macro\n"
        f"{_macro('info', _rich('<p>Hi</p>'))}\n-->\n"
    )
    conversion = await PassthroughConverter().convert(text.encode(), "export.md")

    assert conversion.title == "Original Title"
    assert not conversion.markdown.startswith("---")
    assert conversion.metadata["version"] == 4
    assert conversion.asset_folder == "confluence-5-v4"
    assert conversion.files == ()
    assert conversion.report is not None
    assert "> **Info**" in conversion.markdown
