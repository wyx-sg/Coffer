"""Default file→Markdown engine via MarkItDown.

The ONLY importer of ``markitdown``. The import is lazy so the daemon starts
even when the library is missing; an unhandled format then raises
``EngineUnavailable`` naming the missing dependency.
"""

from __future__ import annotations

import asyncio
import tempfile
from typing import Any

from coffer.domain.errors import EngineUnavailable

# Formats MarkItDown handles well (docs, slides, sheets, pdf, html, …). The
# passthrough/csv converters claim text/csv first in the registry, so this set
# is the "needs an engine" tail.
MARKITDOWN_FORMATS = frozenset(
    {
        "pdf",
        "docx",
        "doc",
        "pptx",
        "ppt",
        "xlsx",
        "xls",
        "html",
        "htm",
        "epub",
        "rtf",
        "odt",
    }
)


class MarkItDownConverter:
    """Implements ``MarkdownConverter`` via the MarkItDown library."""

    def __init__(self) -> None:
        self._md: Any | None = None

    def can_handle(self, fmt: str) -> bool:
        return fmt.lower().lstrip(".") in MARKITDOWN_FORMATS

    def _engine(self) -> Any:
        if self._md is not None:
            return self._md
        try:
            from markitdown import MarkItDown
        except ImportError as exc:  # pragma: no cover - exercised when lib absent
            raise EngineUnavailable(
                "markitdown",
                "install the 'markitdown' package to convert this format",
            ) from exc
        self._md = MarkItDown()
        return self._md

    async def convert(self, data: bytes, fmt: str) -> tuple[str, dict[str, object]]:
        engine = self._engine()
        ext = fmt.lower().lstrip(".")

        def _run() -> str:
            # MarkItDown reads from a path; write the bytes to a temp file with
            # the right suffix so its sniffer dispatches correctly.
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=True) as tmp:
                tmp.write(data)
                tmp.flush()
                result = engine.convert(tmp.name)
                return str(getattr(result, "text_content", "") or "")

        try:
            markdown = await asyncio.to_thread(_run)
        except EngineUnavailable:
            raise
        except Exception as exc:
            raise EngineUnavailable("markitdown", f"conversion failed: {exc}") from exc
        return markdown, {"conversion_engine": "markitdown"}
