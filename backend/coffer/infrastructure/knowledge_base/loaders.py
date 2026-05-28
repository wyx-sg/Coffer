"""Text extraction for ingest. Maps extension -> async extractor.

Failures are raised as domain errors so the surface layer maps them to a
clean HTTP envelope: an unsupported extension is an `IngestRejected`
(client error, 4xx); a missing parser library is an `EngineUnavailable`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from coffer.domain.errors import EngineUnavailable, IngestRejected

# Whitelist of text-extractable extensions and their handler keys.
TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".rst",
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".java",
        ".rs",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cc",
        ".sh",
        ".bash",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
        ".html",
        ".htm",
        ".xml",
        ".css",
        ".scss",
        ".sql",
    }
)

PDF_EXTENSIONS: frozenset[str] = frozenset({".pdf"})

SUPPORTED_EXTENSIONS: frozenset[str] = TEXT_EXTENSIONS | PDF_EXTENSIONS


async def extract_text(path: Path, extension: str) -> str:
    ext = extension.lower()
    if ext in TEXT_EXTENSIONS or ext == "":
        return await asyncio.to_thread(_read_text_file, path)
    if ext in PDF_EXTENSIONS:
        return await asyncio.to_thread(_read_pdf, path)
    raise IngestRejected(
        "unsupported_type",
        f"file extension {ext!r} is not supported for ingest; "
        f"convert to one of: {sorted(SUPPORTED_EXTENSIONS)}",
    )


def _read_text_file(path: Path) -> str:
    # UTF-8 with replacement so unusual files don't blow up the loader.
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise EngineUnavailable(
            "pypdf",
            "PDF support requires the `pypdf` package; "
            "run `pip install pypdf` (or install Coffer with pdf extras)",
        ) from exc
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            # Per-page failure shouldn't fail the whole document; the
            # extracted-text-is-empty check upstream will reject if NO
            # page yielded anything.
            continue
    return "\n\n".join(p.strip() for p in parts if p.strip())


# Function alias for the application service's TextExtractor signature.
TextExtractor = Callable[[Path, str], Awaitable[str]]
