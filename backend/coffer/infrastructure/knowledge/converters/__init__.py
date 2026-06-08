"""Converter substrate: format → Markdown engines behind the
``MarkdownConverter`` port."""

from coffer.infrastructure.knowledge.converters.csv_converter import CsvConverter
from coffer.infrastructure.knowledge.converters.markitdown_converter import (
    MarkItDownConverter,
)
from coffer.infrastructure.knowledge.converters.passthrough_converter import (
    PassthroughConverter,
)
from coffer.infrastructure.knowledge.converters.registry import (
    ConverterRegistry,
    default_registry,
)

__all__ = [
    "ConverterRegistry",
    "CsvConverter",
    "MarkItDownConverter",
    "PassthroughConverter",
    "default_registry",
]
