"""Converter dispatch: content sniffers first, then file extension → the first
``Converter`` that handles it.

A sniffing converter (the Confluence one) claims an upload by what it holds —
a ``.json`` page read result or a ``.storage.xml`` file — before extension
dispatch, so a ``.json`` that is not a Confluence page still passes through and
an ``.xml`` that is not Storage Format stays unsupported. Order matters after
that: passthrough (text/code) and csv claim their formats before the MarkItDown
fallback, so cheap formats never spin up the heavy engine.
"""

from __future__ import annotations

import pathlib
from typing import Protocol, runtime_checkable

from coffer.domain.knowledge.converter import Conversion, Converter, UnsupportedDocument
from coffer.infrastructure.knowledge.converters.confluence import ConfluenceConverter
from coffer.infrastructure.knowledge.converters.csv_converter import CsvConverter
from coffer.infrastructure.knowledge.converters.markitdown_converter import (
    MarkItDownConverter,
)
from coffer.infrastructure.knowledge.converters.passthrough_converter import (
    PassthroughConverter,
)


@runtime_checkable
class SniffingConverter(Converter, Protocol):
    """A converter that claims an upload by its content."""

    def sniff(self, data: bytes, filename: str) -> bool:
        """Whether this converter reads ``data`` (the file named ``filename``)."""
        ...


class ConverterRegistry:
    """Dispatches a file to its converter by extension."""

    def __init__(self, converters: list[Converter]) -> None:
        self._converters = converters

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
        for candidate in self._converters:
            if isinstance(candidate, SniffingConverter) and candidate.sniff(data, filename):
                return await candidate.convert(data, filename)
        fmt = pathlib.Path(filename).suffix.lstrip(".")
        converter = self._resolve(fmt)
        return await converter.convert(data, filename)


def default_registry() -> ConverterRegistry:
    """The production registry: confluence (by content) → passthrough → csv →
    markitdown."""
    return ConverterRegistry(
        [
            ConfluenceConverter(),
            PassthroughConverter(),
            CsvConverter(),
            MarkItDownConverter(),
        ]
    )
