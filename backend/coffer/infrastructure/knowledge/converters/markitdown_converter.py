"""Default file→Markdown engine via MarkItDown.

Spec knowledge "Convert uploads into material without keeping them" names
what it must handle; "Carry no vector or embedding dependency" fences who may
import it.

One of exactly two importers of ``markitdown`` in this codebase — the other is
``infrastructure.chat.document_extract`` for inbound channel attachments — and
the import-linter contract in ``backend/pyproject.toml`` enforces there are no
others. The import is lazy so the daemon starts even when the library is
missing; an unhandled format then raises ``EngineUnavailable`` naming the
missing dependency.
"""

from __future__ import annotations

import asyncio
import pathlib
import tempfile
from typing import Any

from coffer.domain.errors import EngineUnavailable
from coffer.domain.knowledge.converter import Conversion, derive_title

# Formats MarkItDown actually has a converter for (pdf, modern Office, html,
# epub). The passthrough/csv converters claim text/csv first in the registry,
# so this set is the "needs an engine" tail.
#
# Legacy binary Office (.doc/.ppt) and .rtf/.odt are deliberately EXCLUDED:
# MarkItDown has no converter for them (its Docx/Pptx converters accept only
# .docx/.pptx), so claiming them here only turned an "unsupported format" into a
# misleading "engine unavailable / conversion failed". Excluding them lets the
# registry reject them cleanly with an actionable unsupported_type message.
MARKITDOWN_FORMATS = frozenset(
    {
        "pdf",
        "docx",
        "pptx",
        "xlsx",
        "xls",
        "html",
        "htm",
        "epub",
    }
)


class MarkItDownConverter:
    """Implements ``Converter`` via the MarkItDown library."""

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

    async def convert(self, data: bytes, filename: str) -> Conversion:
        engine = self._engine()
        ext = pathlib.Path(filename).suffix.lstrip(".").lower()

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
        return Conversion(
            markdown=markdown, title=derive_title(markdown, filename), converter="markitdown"
        )
