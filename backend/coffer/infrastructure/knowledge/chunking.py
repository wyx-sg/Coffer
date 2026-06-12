"""Markdown-aware chunker.

Splits on ATX headings first (so a chunk never spans two sections), then bounds
each section by ``chunk_size`` with ``chunk_overlap`` carried between adjacent
chunks. ``chunk_size``/``chunk_overlap`` are measured in characters — coarse but
deterministic and dependency-free, which is what the substrate needs (the
embedding model handles real tokenization downstream).
"""

from __future__ import annotations

import re

_HEADING_LINE = re.compile(r"^#{1,6}[ \t]+\S", re.MULTILINE)


def _split_sections(markdown: str) -> list[str]:
    """Split markdown into sections at heading boundaries (heading kept with
    its body)."""
    starts = [m.start() for m in _HEADING_LINE.finditer(markdown)]
    if not starts:
        return [markdown] if markdown.strip() else []
    # Preamble before the first heading, if any.
    bounds = ([0] if starts[0] != 0 else []) + starts + [len(markdown)]
    sections: list[str] = []
    for i in range(len(bounds) - 1):
        section = markdown[bounds[i] : bounds[i + 1]].strip()
        if section:
            sections.append(section)
    return sections


def _bound(section: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Slice one section into <= chunk_size windows with overlap."""
    if len(section) <= chunk_size:
        return [section]
    step = max(1, chunk_size - chunk_overlap)
    chunks: list[str] = []
    for start in range(0, len(section), step):
        piece = section[start : start + chunk_size].strip()
        if piece:
            chunks.append(piece)
        if start + chunk_size >= len(section):
            break
    return chunks


def chunk_markdown(markdown: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Return ordered chunks for ``markdown``.

    Empty/whitespace input yields ``[]``. Overlap is clamped to ``< chunk_size``.
    """
    if not markdown.strip():
        return []
    overlap = max(0, min(chunk_overlap, chunk_size - 1))
    chunks: list[str] = []
    for section in _split_sections(markdown):
        chunks.extend(_bound(section, chunk_size, overlap))
    return chunks
