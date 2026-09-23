"""The document→Markdown conversion layer: pure bytes-and-filename logic.

No file is written and no ``.raw/`` copy is kept here — those belong to the
ingestion pipeline that calls this layer. This tests only what turns bytes into
``Conversion`` (spec knowledge "Convert uploads into material without keeping
them").
"""

from __future__ import annotations

import pytest

from coffer.domain.knowledge.converter import Conversion, UnsupportedDocument, derive_title
from coffer.infrastructure.knowledge.converters.csv_converter import CsvConverter
from coffer.infrastructure.knowledge.converters.passthrough_converter import (
    PassthroughConverter,
)
from coffer.infrastructure.knowledge.converters.registry import default_registry


@pytest.mark.asyncio
async def test_markdown_passthrough_keeps_content_and_picks_up_h1_title() -> None:
    converter = PassthroughConverter()
    data = b"# Account Gateway\n\nWhere account decisions are made.\n"

    result = await converter.convert(data, "notes.md")

    assert isinstance(result, Conversion)
    assert result.markdown == data.decode()
    assert result.title == "Account Gateway"
    assert result.converter == "passthrough"


@pytest.mark.asyncio
async def test_plain_text_passes_through_unchanged_with_filename_title() -> None:
    converter = PassthroughConverter()
    data = b"just some notes, no heading here\n"

    result = await converter.convert(data, "scratch.txt")

    assert result.markdown == data.decode()
    assert result.title == "scratch"
    assert result.converter == "passthrough"


@pytest.mark.asyncio
async def test_csv_becomes_a_markdown_table() -> None:
    converter = CsvConverter()
    data = b"name,role\nAda,engineer\nGrace,engineer\n"

    result = await converter.convert(data, "team.csv")

    assert result.markdown == (
        "| name | role |\n| --- | --- |\n| Ada | engineer |\n| Grace | engineer |\n"
    )
    assert result.title == "team"
    assert result.converter == "csv"


@pytest.mark.asyncio
async def test_csv_escapes_pipes_and_newlines_in_cells() -> None:
    converter = CsvConverter()
    data = b'a|b,"multi\nline"\n'

    result = await converter.convert(data, "weird.csv")

    assert "a\\|b" in result.markdown
    assert "multi line" in result.markdown
    # The embedded newline must not have split the table into an extra row.
    assert result.markdown.count("\n") == 2


@pytest.mark.asyncio
async def test_tsv_uses_tab_delimiter() -> None:
    converter = CsvConverter()
    data = b"name\trole\nAda\tengineer\n"

    result = await converter.convert(data, "team.tsv")

    assert result.markdown == "| name | role |\n| --- | --- |\n| Ada | engineer |\n"


@pytest.mark.asyncio
async def test_registry_dispatches_by_extension_across_converters() -> None:
    registry = default_registry()

    md = await registry.convert(b"# Title\n\nbody\n", "doc.md")
    csv = await registry.convert(b"a,b\n1,2\n", "data.csv")

    assert md.converter == "passthrough"
    assert csv.converter == "csv"


@pytest.mark.asyncio
async def test_registry_supports_reports_known_extensions() -> None:
    registry = default_registry()

    assert registry.supports(".md") is True
    assert registry.supports("CSV") is True
    assert registry.supports(".pdf") is True
    assert registry.supports(".doc") is False


@pytest.mark.asyncio
async def test_unsupported_extension_raises_unsupported_document_naming_the_type() -> None:
    registry = default_registry()

    with pytest.raises(UnsupportedDocument) as exc_info:
        await registry.convert(b"whatever", "legacy.doc")

    assert exc_info.value.doc_type == "doc"
    assert "doc" in str(exc_info.value)


def test_derive_title_falls_back_to_the_file_name_with_no_heading() -> None:
    assert derive_title("just prose, no heading\n", "My Report.pdf") == "My Report"


def test_derive_title_ignores_a_heading_that_is_not_the_first_line() -> None:
    text = "some intro text\n\n# Not The Title\n"
    assert derive_title(text, "fallback-name.md") == "fallback-name"


def test_derive_title_skips_leading_blank_lines() -> None:
    text = "\n\n# Real Title\n\nbody\n"
    assert derive_title(text, "whatever.md") == "Real Title"
