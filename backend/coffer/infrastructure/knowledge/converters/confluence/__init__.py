"""Confluence pages as readable sources (spec knowledge "Import a Confluence
page as a readable source with its attachments")."""

from __future__ import annotations

from coffer.domain.knowledge.converter import Conversion
from coffer.infrastructure.knowledge.converters.confluence import page


class ConfluenceConverter:
    """Implements ``Converter`` for a Confluence page export (JSON).

    Claimed by content, not by extension: a ``.json`` file is a page export
    only when it reads as one (:func:`page.read`); any other JSON goes on to
    the passthrough converter as text.
    """

    def can_handle(self, fmt: str) -> bool:
        # Never by extension alone: see `claims`.
        return False

    def claims(self, data: bytes, fmt: str) -> bool:
        return fmt.lower().lstrip(".") == "json" and page.read(data) is not None

    async def convert(self, data: bytes, filename: str) -> Conversion:
        found = page.read(data)
        if found is None:  # pragma: no cover - the registry asks `claims` first
            raise ValueError(f"{filename!r} is not a Confluence page export")
        return page.convert(found)


__all__ = ["ConfluenceConverter"]
