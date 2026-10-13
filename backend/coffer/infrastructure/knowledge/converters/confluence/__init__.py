"""Confluence page import: Storage Format → readable Markdown (design §5, §6).

Coffer never calls Confluence. The person uploads what they fetched — a page
read result in JSON, a ``*.storage.xml`` file, or a Markdown file carrying
``skynet-confluence-storage:v1`` markers — and this package turns its Storage
XML into Markdown, keeping the pictures and diagram sources the body shows and
listing what it could not keep. Nothing is executed and nothing is fetched.
"""

from __future__ import annotations

from coffer.infrastructure.knowledge.converters.confluence.converter import (
    ConfluenceConverter,
    convert_export,
)
from coffer.infrastructure.knowledge.converters.confluence.export import (
    StorageInput,
    parse_export,
)
from coffer.infrastructure.knowledge.converters.confluence.markers import (
    STORAGE_MARKER,
    expand_storage_markers,
)

__all__ = [
    "STORAGE_MARKER",
    "ConfluenceConverter",
    "StorageInput",
    "convert_export",
    "expand_storage_markers",
    "parse_export",
]
