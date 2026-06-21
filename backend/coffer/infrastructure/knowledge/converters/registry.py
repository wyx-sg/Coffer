"""Converter dispatch: format → the first ``MarkdownConverter`` that handles it.

Order matters: passthrough (text/code) and csv claim their formats before the
MarkItDown fallback, so cheap formats never spin up the heavy engine.
"""

from __future__ import annotations

from coffer.domain.errors import IngestRejected
from coffer.domain.knowledge.converter import MarkdownConverter
from coffer.infrastructure.knowledge.cleaning import clean_markdown
from coffer.infrastructure.knowledge.converters.csv_converter import CsvConverter
from coffer.infrastructure.knowledge.converters.markitdown_converter import (
    MarkItDownConverter,
)
from coffer.infrastructure.knowledge.converters.passthrough_converter import (
    PassthroughConverter,
)


class ConverterRegistry:
    """Dispatches a format to its converter and cleans the result."""

    def __init__(self, converters: list[MarkdownConverter]) -> None:
        self._converters = converters

    def supports(self, fmt: str) -> bool:
        norm = fmt.lower().lstrip(".")
        return any(c.can_handle(norm) for c in self._converters)

    def _resolve(self, fmt: str) -> MarkdownConverter:
        norm = fmt.lower().lstrip(".")
        for converter in self._converters:
            if converter.can_handle(norm):
                return converter
        raise IngestRejected(
            "unsupported_type",
            f"Unsupported file type {fmt!r}. Convert it to a supported format — "
            "PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx/.xls), HTML, "
            "EPUB, CSV, or a text/Markdown file — and re-upload. Legacy Office "
            "files (.doc/.ppt) must be saved as .docx/.pptx first.",
        )

    async def convert(self, data: bytes, fmt: str) -> tuple[str, dict[str, object]]:
        """Convert + clean. Returns ``(clean_markdown, metadata)``.

        Raises ``IngestRejected('unsupported_type')`` if no converter handles
        the format. An empty conversion raises ``IngestRejected('scanned_pdf')``
        for PDFs (an actionable "this looks scanned/image-only, run OCR"
        message) and ``IngestRejected('empty')`` for every other format.
        ``EngineUnavailable`` propagates from the engine.
        """
        converter = self._resolve(fmt)
        raw, meta = await converter.convert(data, fmt)
        markdown = clean_markdown(raw)
        if not markdown.strip():
            if fmt.lower().lstrip(".") == "pdf":
                raise IngestRejected(
                    "scanned_pdf",
                    "This PDF has no extractable text — it looks scanned or "
                    "image-only. Run OCR (or convert it to a text-based PDF) "
                    "and re-upload.",
                )
            raise IngestRejected("empty", f"conversion of {fmt!r} produced empty markdown")
        return markdown, meta


def default_registry() -> ConverterRegistry:
    """The production registry: passthrough → csv → markitdown."""
    return ConverterRegistry(
        [
            PassthroughConverter(),
            CsvConverter(),
            MarkItDownConverter(),
        ]
    )
