"""Storage markers in a Markdown export expand in place (design §6).

The fixture reproduces the marker shapes of a real Markdown export with
placeholder text only.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.knowledge.converters.confluence import expand_storage_markers

FIXTURES = pathlib.Path(__file__).parents[2] / "fixtures" / "knowledge" / "confluence"
FORBIDDEN = ("<ac:", "<ri:", "skynet-confluence-storage", "CDATA", "<script", "<iframe", "<!--")


def _marker(xml: str) -> str:
    escaped = xml.replace("\\", "\\\\").replace("--", "\\u002d\\u002d")
    return f"<!-- skynet-confluence-storage:v1 kind=structured-macro\n{escaped}\n-->"


@pytest.mark.acceptance(
    spec="knowledge", scenario="a source holding storage markers reads as Markdown"
)
def test_markers_fixture_expands_to_headings_tables_and_text() -> None:
    markdown, issues = expand_storage_markers((FIXTURES / "page-markers.md").read_text())

    for needle in FORBIDDEN:
        assert needle not in markdown, needle
    assert markdown.startswith("# Basic Info\n\n| Service Name | service-c |")
    assert "| **Repository** | [service-c](https://git.example.com/service-c) |" in markdown
    assert "Service C keeps the *examples*." in markdown
    assert "## Screens" in markdown
    # Text the export had already converted is left as it was.
    assert "# Plain Section\n\nText the export already converted.\n\n" in markdown
    assert markdown.endswith("[Diagram source](https://drive.example.com/file/placeholder)\n")
    assert [(i.kind, i.name, i.reason) for i in issues] == [
        ("missing_attachment", "screen.png", "not kept by the Markdown export"),
        ("missing_attachment", "diagram-1.drawio", "not kept by the Markdown export"),
    ]


def test_markdown_without_markers_is_returned_unchanged() -> None:
    text = "# Title\n\n<!-- an ordinary comment -->\n\nbody\n"
    assert expand_storage_markers(text) == (text, ())


def test_escaped_dashes_and_backslashes_are_restored_inside_code() -> None:
    xml = (
        '<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">sql</ac:parameter>'
        "<ac:plain-text-body><![CDATA[SELECT 1 -- note\nC:\\path]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )
    markdown, issues = expand_storage_markers("before\n\n" + _marker(xml) + "\n\nafter\n")
    assert markdown == "before\n\n```sql\nSELECT 1 -- note\nC:\\path\n```\n\nafter\n"
    assert issues == ()


def test_a_marker_that_converts_to_nothing_leaves_the_text_around_it() -> None:
    toc = '<ac:structured-macro ac:name="toc" ac:schema-version="1" />'
    markdown, _ = expand_storage_markers(_marker(toc) + "\n\n# Heading\n")
    assert markdown == "# Heading\n"


def test_marker_glued_to_the_next_text_is_separated() -> None:
    info = (
        '<ac:structured-macro ac:name="info"><ac:rich-text-body><p>note</p>'
        "</ac:rich-text-body></ac:structured-macro>"
    )
    markdown, _ = expand_storage_markers("intro" + _marker(info) + "[link](https://example.com)")
    assert markdown == "intro\n\n> **Info:**\n>\n> note\n\n[link](https://example.com)"
