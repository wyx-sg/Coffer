"""Storage Format → Markdown, one test per row of the design §5 element table.

Spec knowledge (change keep-knowledge-files-in-place-and-import-readable-sources),
design §5 "Storage → Markdown". Every input here is synthetic.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.knowledge.converter import Conversion
from coffer.infrastructure.knowledge.converters.confluence import StorageInput, convert_export

NOW = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
FORBIDDEN = ("<ac:", "<ri:", "skynet-confluence-storage", "CDATA", "<script", "<iframe")


def convert(storage: str, attachments: dict[str, bytes] | None = None) -> Conversion:
    inp = StorageInput(
        title="Example Page",
        body=storage,
        page_id="1",
        version=1,
        attachments=attachments or {},
    )
    result = convert_export(inp, now=NOW)
    for needle in FORBIDDEN:
        assert needle not in result.markdown, needle
    return result


def macro(name: str, inner: str = "", *, params: dict[str, str] | None = None) -> str:
    rendered = "".join(
        f'<ac:parameter ac:name="{k}">{v}</ac:parameter>' for k, v in (params or {}).items()
    )
    if not inner and not rendered:
        return f'<ac:structured-macro ac:name="{name}" ac:schema-version="1" />'
    opening = f'<ac:structured-macro ac:name="{name}" ac:schema-version="1">'
    return f"{opening}{rendered}{inner}</ac:structured-macro>"


def rich(body: str) -> str:
    return f"<ac:rich-text-body>{body}</ac:rich-text-body>"


def plain(text: str) -> str:
    return f"<ac:plain-text-body><![CDATA[{text}]]></ac:plain-text-body>"


def kinds(result: Conversion) -> list[tuple[str, str]]:
    return [(i.kind, i.name) for i in result.issues]


@pytest.mark.acceptance(spec="knowledge", scenario="macros never swallow headings, tables or code")
def test_numberedheadings_wrapping_the_whole_body_keeps_headings_tables_and_paragraphs() -> None:
    body = macro(
        "numberedheadings",
        rich(
            "<h1>Basic Info</h1>"
            "<table><tbody><tr><th>Name</th><td>service-a</td></tr></tbody></table>"
            "<h2>Details</h2><p>Some <strong>bold</strong> text.</p>"
        ),
    )
    result = convert(macro("easy-heading-free") + body)

    assert "# Basic Info" in result.markdown
    assert "## Details" in result.markdown
    assert "| Name | service-a |" in result.markdown
    assert "Some **bold** text." in result.markdown
    assert result.issues == ()


@pytest.mark.parametrize("name", ["section", "column", "details"])
def test_layout_macros_are_unwrapped_without_an_issue(name: str) -> None:
    result = convert(macro(name, rich("<p>inside</p>")))
    assert result.markdown.strip() == "inside"
    assert result.issues == ()


@pytest.mark.parametrize("name", ["toc", "children", "pagetree", "anchor"])
def test_navigation_macros_become_nothing(name: str) -> None:
    result = convert(f"<p>{macro(name)}</p><p>after</p>")
    assert result.markdown.strip() == "after"
    assert result.issues == ()


def test_toc_with_macro_id_before_name_is_still_dropped() -> None:
    storage = '<p><ac:structured-macro ac:macro-id="x-1" ac:name="toc" ac:schema-version="1" /></p>'
    assert convert(storage).markdown.strip() == ""


def test_expand_is_its_title_in_bold_then_its_body() -> None:
    result = convert(macro("expand", rich("<p>hidden</p>"), params={"title": "More"}))
    assert result.markdown.strip() == "**More**\n\nhidden"


@pytest.mark.parametrize(
    ("name", "label"), [("info", "Info"), ("note", "Note"), ("tip", "Tip"), ("warning", "Warning")]
)
def test_panels_become_a_labelled_blockquote(name: str, label: str) -> None:
    result = convert(macro(name, rich("<p>careful</p>")))
    assert result.markdown.strip() == f"> **{label}:**\n>\n> careful"


def test_panel_uses_its_own_title() -> None:
    result = convert(macro("panel", rich("<p>x</p>"), params={"title": "Heads up"}))
    assert result.markdown.startswith("> **Heads up:**")


def test_inline_comment_marker_keeps_its_text() -> None:
    storage = macro(
        "info",
        rich(
            '<ul><li><ac:inline-comment-marker ac:ref="r1">open the console'
            "</ac:inline-comment-marker></li></ul>"
        ),
    )
    assert "> - open the console" in convert(storage).markdown


@pytest.mark.acceptance(spec="knowledge", scenario="macros never swallow headings, tables or code")
def test_code_keeps_its_text_verbatim_and_its_language() -> None:
    code = "run service-a-<module>-<env> && echo 'a < b'\n  indented"
    result = convert(macro("code", plain(code), params={"language": "bash"}))
    assert result.markdown.strip() == f"```bash\n{code}\n```"


def test_noformat_is_a_plain_fence_and_backticks_lengthen_it() -> None:
    result = convert(macro("noformat", plain("a ``` b")))
    assert result.markdown.strip() == "````\na ``` b\n````"


@pytest.mark.acceptance(spec="knowledge", scenario="macros never swallow headings, tables or code")
def test_code_inside_a_table_cell_stays_intact_with_its_language() -> None:
    cell = macro(
        "code", plain("example-cli enter service-a-<module>-<env>-xx"), params={"language": "bash"}
    )
    storage = f"<table><tbody><tr><th>Logs</th><td><div>{cell}</div></td></tr></tbody></table>"
    result = convert(storage)
    assert "```bash\nexample-cli enter service-a-<module>-<env>-xx\n```" in result.markdown
    assert "<th>Logs</th>" in result.markdown


def test_status_is_its_title_in_backticks_and_jira_is_its_key() -> None:
    storage = (
        f"<p>Ticket {macro('jira', params={'server': 'Example', 'key': 'ABC-1'})} is "
        f"{macro('status', params={'colour': 'Blue', 'title': 'Done'})}.</p>"
    )
    assert convert(storage).markdown.strip() == "Ticket ABC-1 is `Done`."


def test_plantuml_is_fenced_kept_as_puml_and_not_rendered() -> None:
    result = convert(macro("plantuml", plain("@startuml\nA -> B\n@enduml")))
    assert "```plantuml\n@startuml\nA -> B\n@enduml\n```" in result.markdown
    puml = [f for f in result.files if f.name.endswith(".puml")]
    assert [f.data for f in puml] == [b"@startuml\nA -> B\n@enduml"]
    assert kinds(result) == [("not_rendered", puml[0].name)]
    assert result.metadata["import_status"] == "complete"


def test_drawio_shows_its_picture_and_keeps_its_source() -> None:
    attachments = {"flow.png": b"PNG", "flow": b"<mxfile/>"}
    result = convert(macro("drawio", params={"diagramName": "flow"}), attachments)
    assert "![flow](coffer-asset:flow.png)" in result.markdown
    assert "(coffer-asset:flow.drawio)" in result.markdown
    assert {f.name: f.data for f in result.files}["flow.drawio"] == b"<mxfile/>"
    assert result.issues == ()


def test_drawio_without_its_attachment_is_missing() -> None:
    result = convert(macro("drawio", params={"diagramName": "flow"}))
    assert kinds(result) == [("missing_attachment", "flow")]
    assert result.metadata["import_status"] == "partial"


def test_inc_drawio_names_a_diagram_on_another_page() -> None:
    result = convert(macro("inc-drawio", params={"diagramName": "flow", "pageId": "9"}))
    assert ("missing_attachment", "flow") in kinds(result)
    assert all(i.reason == "on another page" for i in result.issues)


def test_any_other_html_macro_is_not_kept() -> None:
    result = convert(macro("html", plain("<script>alert(1)</script><b>x</b>")))
    assert "An HTML block was not kept." in result.markdown
    assert kinds(result) == [("unsupported_macro", "html")]


def test_attached_picture_is_kept_under_a_safe_name() -> None:
    storage = (
        '<p><ac:image ac:width="860">'
        '<ri:attachment ri:filename="my arch (v2).png" /></ac:image></p>'
    )
    result = convert(storage, {"my arch (v2).png": b"PNG"})
    assert "![my arch (v2).png](coffer-asset:my-arch-v2-.png)" in result.markdown
    assert [f.name for f in result.files] == ["page.storage.xml", "my-arch-v2-.png"]


@pytest.mark.parametrize(
    "attrs", ['ac:style="max-height: 250.0px;"', 'ac:height="250"', 'ac:alt="Screen"']
)
def test_image_variants_all_show_the_attachment(attrs: str) -> None:
    storage = f'<p><ac:image {attrs}><ri:attachment ri:filename="s.png" /></ac:image></p>'
    result = convert(storage, {"s.png": b"PNG"})
    assert "(coffer-asset:s.png)" in result.markdown


@pytest.mark.acceptance(
    spec="knowledge", scenario="what an import could not keep is listed with its reason"
)
def test_missing_and_cross_page_pictures_are_listed() -> None:
    storage = (
        '<p><ac:image><ri:attachment ri:filename="gone.png" /></ac:image></p>'
        '<p><ac:image><ri:attachment ri:filename="o.png"><ri:page ri:content-title="Other" />'
        "</ri:attachment></ac:image></p>"
    )
    result = convert(storage)
    assert [(i.kind, i.name, i.reason) for i in result.issues] == [
        ("missing_attachment", "gone.png", "not in the export"),
        ("missing_attachment", "o.png", "on another page"),
    ]
    records = result.metadata["attachments"]
    assert {"name": "gone.png", "status": "missing", "reason": "not in the export"} in records  # type: ignore[operator]


def test_remote_picture_is_a_link_never_an_embedded_image() -> None:
    storage = '<p><ac:image><ri:url ri:value="https://img.example.com/a.png" /></ac:image></p>'
    result = convert(storage)
    assert "[Picture](https://img.example.com/a.png)" in result.markdown
    assert "![" not in result.markdown
    assert kinds(result) == [("external_image", "https://img.example.com/a.png")]


@pytest.mark.parametrize(
    ("ref", "text"),
    [
        ('<ri:page ri:space-key="EXA" ri:content-title="Circuit Breaker" />', "Circuit Breaker"),
        ('<ri:attachment ri:filename="spec.pdf" />', "spec.pdf"),
        ('<ri:user ri:userkey="abc123" />', "@user"),
        ('<ri:user ri:username="jdoe" />', "@jdoe"),
    ],
)
def test_links_become_their_text(ref: str, text: str) -> None:
    result = convert(f"<p>See <ac:link>{ref}</ac:link>.</p>")
    assert result.markdown.strip() == f"See {text}."


def test_link_body_wins_over_the_target() -> None:
    storage = (
        '<p><ac:link><ri:page ri:content-title="T" />'
        "<ac:plain-text-link-body><![CDATA[the label]]></ac:plain-text-link-body></ac:link></p>"
    )
    assert convert(storage).markdown.strip() == "the label"


def test_emoticon_and_placeholder() -> None:
    storage = '<p>ok <ac:emoticon ac:name="smile" /><ac:placeholder>type here</ac:placeholder></p>'
    assert convert(storage).markdown.strip() == "ok :smile:"


def test_task_list_becomes_checkboxes() -> None:
    storage = (
        "<ac:task-list><ac:task><ac:task-status>complete</ac:task-status>"
        "<ac:task-body>done thing</ac:task-body></ac:task><ac:task>"
        "<ac:task-status>incomplete</ac:task-status><ac:task-body>open thing</ac:task-body>"
        "</ac:task></ac:task-list>"
    )
    assert convert(storage).markdown.strip() == "- [x] done thing\n- [ ] open thing"


def test_table_with_merged_cells_is_a_sanitised_html_table() -> None:
    storage = (
        '<table class="wrapped"><colgroup><col /></colgroup><tbody>'
        '<tr><th colspan="2" style="x">Head</th></tr>'
        '<tr><td rowspan="2" onclick="x()">A</td><td>B</td></tr></tbody></table>'
    )
    markdown = convert(storage).markdown
    assert '<th colspan="2">Head</th>' in markdown
    assert '<td rowspan="2">A</td>' in markdown
    for bad in ("style=", "onclick", "class=", "colgroup"):
        assert bad not in markdown


def test_plain_table_is_a_markdown_table() -> None:
    storage = (
        "<table><tbody><tr><th>K</th><th>V</th></tr>"
        "<tr><td>a | b</td><td><p>one</p><p>two</p></td></tr></tbody></table>"
    )
    markdown = convert(storage).markdown
    assert "| K | V |\n| --- | --- |\n| a \\| b | one<br><br>two |" in markdown


def test_unknown_macro_keeps_its_body_and_is_listed() -> None:
    result = convert(macro("fancy-box", rich("<p>Kept body text.</p>")))
    assert result.markdown.strip() == "Kept body text."
    assert kinds(result) == [("unsupported_macro", "fancy-box")]


def test_unknown_body_less_macro_is_listed() -> None:
    result = convert(macro("mystery-widget"))
    assert kinds(result) == [("unsupported_macro", "mystery-widget")]
    assert "mystery-widget" in result.markdown


def test_text_cannot_start_raw_html_or_a_wiki_link() -> None:
    result = convert("<p>a &lt;script&gt; and [[not a link]] and *x*</p>")
    assert "<script" not in result.markdown
    assert "[[" not in result.markdown
    assert "\\*x\\*" in result.markdown


def test_unsafe_link_target_keeps_only_its_text() -> None:
    result = convert('<p><a href="javascript:alert(1)">click</a></p>')
    assert result.markdown.strip() == "click"
