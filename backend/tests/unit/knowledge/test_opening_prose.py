"""A description drawn from a document's opening prose skips what is not prose
(spec knowledge "Fill frontmatter on converted material")."""

from __future__ import annotations

from coffer.infrastructure.knowledge.naming import opening_prose


def test_tables_html_pictures_and_code_are_not_prose() -> None:
    markdown = (
        "# Service A\n\n"
        "| key | value |\n| --- | --- |\n| a | b |\n\n"
        "<table>\n  <tr><td>x</td></tr>\n</table>\n\n"
        "![chart](../assets/a/c.png)\n\n"
        "> **Info:** a panel\n\n"
        "```bash\nrun it\n```\n\n"
        "Service A keeps the records.\nIt answers lookups.\n\n"
        "Later paragraph."
    )
    assert opening_prose(markdown, fallback="Service A") == (
        "Service A keeps the records. It answers lookups."
    )


def test_a_document_with_no_prose_falls_back_to_its_title() -> None:
    assert opening_prose("| a |\n| - |\n\n<div>x</div>", fallback="Title") == "Title"


def test_markdown_inside_an_html_table_is_not_prose() -> None:
    markdown = (
        "<table>\n<tr>\n<td>\n\n[account](https://example.com/a)\n\n</td>\n</tr>\n</table>\n\n"
        "The service owns accounts."
    )
    assert opening_prose(markdown, fallback="T") == "The service owns accounts."


def test_labels_links_lists_and_placeholders_are_not_prose() -> None:
    markdown = (
        "link: [https://example.com/a](https://example.com/a)\n\n"
        "**diagram source**\n\n"
        "[Diagram: d.drawio](../assets/a/d.drawio)\n\n"
        "- URL: [x](https://example.com)\n\n"
        "1. First step\n\n"
        "\\[Personal contact table omitted\\]\n\n"
        "See [the topic list](https://example.com/t) for every event."
    )
    assert opening_prose(markdown, fallback="T") == (
        "See [the topic list](https://example.com/t) for every event."
    )


def test_lines_of_labelled_links_and_notices_are_not_prose() -> None:
    markdown = (
        "Monitoring: [https://example.com/a](https://example.com/a)\\\n"
        "Canary: [https://example.com/b](https://example.com/b)\n\n"
        "*Picture not kept: image_2025-9-8.png*\n\n"
        "The service keeps consent records."
    )
    assert opening_prose(markdown, fallback="T") == "The service keeps consent records."
