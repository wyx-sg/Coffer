"""Unit tests for converter dispatch + cleaning. Pure (no engine libs needed)."""

import pytest

from coffer.domain.errors import IngestRejected
from coffer.infrastructure.knowledge.converters import default_registry
from coffer.infrastructure.knowledge.converters.csv_converter import CsvConverter
from coffer.infrastructure.knowledge.converters.markitdown_converter import (
    MarkItDownConverter,
)
from coffer.infrastructure.knowledge.converters.passthrough_converter import (
    PassthroughConverter,
)
from coffer.infrastructure.knowledge.converters.registry import ConverterRegistry


class _EmptyConverter:
    """Fake converter that claims one format and always yields empty markdown."""

    def __init__(self, fmt: str) -> None:
        self._fmt = fmt

    def can_handle(self, fmt: str) -> bool:
        return fmt == self._fmt

    async def convert(self, data: bytes, fmt: str) -> tuple[str, dict[str, object]]:
        return "", {"conversion_engine": "fake"}


@pytest.mark.asyncio
async def test_passthrough_handles_markdown_and_code() -> None:
    reg = default_registry()
    md, meta = await reg.convert(b"# Title\n\nbody", "md")
    assert "# Title" in md
    assert meta["conversion_engine"] == "passthrough"
    code, _ = await reg.convert(b"def f():\n    return 1\n", "py")
    assert "def f" in code


@pytest.mark.asyncio
async def test_csv_renders_markdown_table() -> None:
    out, meta = await CsvConverter().convert(b"a,b\n1,2\n3,4\n", "csv")
    assert "| a | b |" in out
    assert "| --- | --- |" in out
    assert "| 1 | 2 |" in out
    assert meta["conversion_engine"] == "csv"


@pytest.mark.asyncio
async def test_registry_routes_csv_before_markitdown() -> None:
    reg = default_registry()
    out, meta = await reg.convert(b"x,y\n1,2\n", "csv")
    assert meta["conversion_engine"] == "csv"
    assert "| x | y |" in out


@pytest.mark.asyncio
async def test_unsupported_format_rejected() -> None:
    reg = default_registry()
    with pytest.raises(IngestRejected) as exc:
        await reg.convert(b"\x00\x01", "xyz")
    assert exc.value.reason == "unsupported_type"


@pytest.mark.asyncio
async def test_empty_conversion_rejected() -> None:
    reg = default_registry()
    with pytest.raises(IngestRejected) as exc:
        await reg.convert(b"   \n\n  ", "txt")
    assert exc.value.reason == "empty"


@pytest.mark.asyncio
async def test_empty_pdf_conversion_rejected_as_scanned() -> None:
    # A scanned / image-only PDF converts to empty markdown — surface an
    # actionable scanned_pdf reason (KB11) instead of the generic "empty".
    reg = ConverterRegistry([_EmptyConverter("pdf")])
    with pytest.raises(IngestRejected) as exc:
        await reg.convert(b"%PDF-1.4 ...", "pdf")
    assert exc.value.reason == "scanned_pdf"
    assert "ocr" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_empty_pdf_with_dot_prefix_rejected_as_scanned() -> None:
    # The fmt may arrive as ".pdf" (extension form); the registry normalises it
    # both for converter dispatch and for the scanned-PDF reason branch.
    reg = ConverterRegistry([_EmptyConverter("pdf")])
    with pytest.raises(IngestRejected) as exc:
        await reg.convert(b"%PDF-1.4 ...", ".pdf")
    assert exc.value.reason == "scanned_pdf"


@pytest.mark.asyncio
async def test_empty_non_pdf_conversion_still_generic_empty() -> None:
    # Non-PDF empty conversions keep the generic "empty" reason.
    reg = ConverterRegistry([_EmptyConverter("docx")])
    with pytest.raises(IngestRejected) as exc:
        await reg.convert(b"PK...", "docx")
    assert exc.value.reason == "empty"


def test_passthrough_can_handle_strips_dot() -> None:
    assert PassthroughConverter().can_handle(".md") is True
    assert PassthroughConverter().can_handle("MD") is True
    assert PassthroughConverter().can_handle("pdf") is False


def test_registry_supports() -> None:
    reg = default_registry()
    assert reg.supports("csv") is True
    assert reg.supports("pdf") is True  # markitdown claims it (lazy)
    assert reg.supports("zzz") is False
    assert reg.supports("doc") is False  # legacy Office: no converter exists


def test_markitdown_drops_legacy_office_formats() -> None:
    # Legacy binary Office (.doc/.ppt) + .rtf/.odt have NO MarkItDown converter.
    # Claiming them produced a misleading "engine unavailable / conversion
    # failed" error; instead they must fall through to the registry's clean
    # unsupported_type path. The formats MarkItDown actually reads stay claimed.
    conv = MarkItDownConverter()
    for fmt in ("doc", "ppt", "rtf", "odt"):
        assert conv.can_handle(fmt) is False, fmt
    for fmt in ("pdf", "docx", "pptx", "xlsx", "xls", "html", "htm", "epub"):
        assert conv.can_handle(fmt) is True, fmt


@pytest.mark.asyncio
async def test_legacy_office_rejected_with_actionable_message() -> None:
    # A legacy .doc/.ppt (or .rtf/.odt) upload is rejected as unsupported_type
    # with a message that tells the user how to proceed (save as .docx/.pptx).
    reg = default_registry()
    for fmt in ("doc", "ppt", "rtf", "odt"):
        with pytest.raises(IngestRejected) as exc:
            await reg.convert(b"\xd0\xcf\x11\xe0", fmt)
        assert exc.value.reason == "unsupported_type", fmt
        msg = str(exc.value).lower()
        assert ".docx" in msg or "supported" in msg, fmt
