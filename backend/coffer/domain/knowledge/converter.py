"""The ``MarkdownConverter`` port — what Coffer needs from a file→Markdown
engine, so concrete engines (MarkItDown, passthrough, csv→table) stay in
``infrastructure/knowledge/converters/``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MarkdownConverter(Protocol):
    """Converts an uploaded file's bytes to clean Markdown + metadata."""

    def can_handle(self, fmt: str) -> bool:
        """Whether this converter handles the given lower-cased format/ext."""
        ...

    async def convert(self, data: bytes, fmt: str) -> tuple[str, dict[str, object]]:
        """Return ``(markdown, metadata)``.

        ``metadata`` may carry per-engine provenance (e.g.
        ``conversion_engine``). Raises ``EngineUnavailable`` if the underlying
        library is missing.
        """
        ...
