"""Converter dispatch: file extension → the first ``Converter`` that handles it.

Order matters: passthrough (text/code) and csv claim their formats before the
MarkItDown fallback, so cheap formats never spin up the heavy engine.
"""

from __future__ import annotations

import pathlib

from coffer.domain.knowledge.converter import Conversion, Converter, UnsupportedDocument
from coffer.infrastructure.knowledge.converters.csv_converter import CsvConverter
from coffer.infrastructure.knowledge.converters.markitdown_converter import (
    MarkItDownConverter,
)
from coffer.infrastructure.knowledge.converters.passthrough_converter import (
    PassthroughConverter,
)


class ConverterRegistry:
    """Dispatches a file to its converter by extension."""

    def __init__(self, converters: list[Converter]) -> None:
        self._converters = converters

    def supports(self, fmt: str) -> bool:
        norm = fmt.lower().lstrip(".")
        return any(c.can_handle(norm) for c in self._converters)

    def _resolve(self, fmt: str) -> Converter:
        norm = fmt.lower().lstrip(".")
        for converter in self._converters:
            if converter.can_handle(norm):
                return converter
        raise UnsupportedDocument(norm)

    async def convert(self, data: bytes, filename: str) -> Conversion:
        """Convert ``data`` (the file named ``filename``) to Markdown.

        Raises ``UnsupportedDocument`` naming the extension when no converter
        handles it — never a half-conversion.
        """
        fmt = pathlib.Path(filename).suffix.lstrip(".")
        converter = self._resolve(fmt)
        return await converter.convert(data, filename)


def default_registry() -> ConverterRegistry:
    """The production registry: passthrough → csv → markitdown."""
    return ConverterRegistry(
        [
            PassthroughConverter(),
            CsvConverter(),
            MarkItDownConverter(),
        ]
    )
