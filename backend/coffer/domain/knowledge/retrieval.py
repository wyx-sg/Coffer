"""Pure semantic-retrieval ranking for the knowledge layer (spec knowledge FR-024).

No filesystem, no network, no embedding provider: this module turns a body of
Markdown into embeddable sections, and turns a query vector plus a pool of
per-section vectors into a ranked, one-hit-per-file result. Fetching the
vectors (the internal connection, FR-026) and storing them (the disposable
sidecar, FR-025) both live in infrastructure; this module has no opinion on
either — it is pure enough to unit-test with hand-written float lists.

``split_sections`` deliberately does far less than the chunker it replaces
(the deleted database-backed passage chunker): no cross-chunk overlap, no
atomic fenced-code/table handling, no sentence-level splitting of an
oversized paragraph. The corpus this serves is hundreds of hand-written
knowledge files, retrieval always returns whole files rather than passage
fragments (FR-023/FR-024), and a section vector only has to be good enough to
rank its *file* — it never has to stand alone as a citation. A heading plus
its body, capped at a size one embedding call can take in one shot, is
already enough for that job.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

#: An ATX heading: 1-6 ``#`` then required whitespace then non-whitespace
#: content — CommonMark's rule, so a bare ``#`` or a ``#tag`` in prose is not
#: a heading.
_ATX_HEADING = re.compile(r"^#{1,6}[ \t]+(\S.*)$")

#: Default cap for :func:`split_sections`. Large enough that a typical
#: knowledge-file section survives whole (one embedding call, one vector);
#: small enough to stay well inside any embedding endpoint's input limit.
DEFAULT_MAX_CHARS = 2000

#: Hits returned per :func:`rank` call. The catalogue already answers "what
#: exists" a level at a time (FR-021); this is `search`'s analogue — enough
#: results to scan on one screen without turning a semantic query into a
#: second full-corpus dump. A caller that wants fewer passes a smaller
#: ``top_k``; nothing here needs more by default.
DEFAULT_TOP_K = 8

#: Cosine-similarity floor below which a hit is treated as noise rather than a
#: match. Unrelated natural-language passages embedded by general-purpose
#: text-embedding models typically land well under 0.2; genuine matches for a
#: specific query commonly clear 0.3-0.4+. The floor is deliberately
#: conservative — FR-027 already provides a literal-search fallback for "search
#: found nothing", so this constant only has to reject noise, never chase
#: recall.
DEFAULT_MIN_SCORE = 0.2


@dataclass(frozen=True)
class Section:
    """One embeddable slice of a file's body: a heading and the text under it."""

    heading: str  # "" for the lead section before the first heading
    text: str  # what gets embedded: the heading line plus its body
    start_line: int  # 1-based line number of the section's first line


def _heading_text(line: str) -> str:
    """The heading's own text, ``#``s and any trailing closing sequence stripped."""
    match = _ATX_HEADING.match(line)
    if match is None:
        return ""
    return re.sub(r"[ \t]+#+$", "", match.group(1)).strip()


def _raw_sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """``(heading, start_idx, end_idx)`` spans over 0-based ``lines`` (end exclusive).

    Text before the first heading — if any — is its own span with
    ``heading=""``. A body with no heading at all is one span covering
    everything.
    """
    heading_idxs = [i for i, line in enumerate(lines) if _ATX_HEADING.match(line)]
    if not heading_idxs:
        return [("", 0, len(lines))]
    spans: list[tuple[str, int, int]] = []
    if heading_idxs[0] != 0:
        spans.append(("", 0, heading_idxs[0]))
    for pos, start in enumerate(heading_idxs):
        end = heading_idxs[pos + 1] if pos + 1 < len(heading_idxs) else len(lines)
        spans.append((_heading_text(lines[start]), start, end))
    return spans


def _paragraphs(lines: list[str]) -> list[tuple[list[str], int]]:
    """Consecutive non-blank-line runs, each paired with its 0-based start offset."""
    blocks: list[tuple[list[str], int]] = []
    i, n = 0, len(lines)
    while i < n:
        if not lines[i].strip():
            i += 1
            continue
        start = i
        while i < n and lines[i].strip():
            i += 1
        blocks.append((lines[start:i], start))
    return blocks


def _pack_paragraphs(
    paragraphs: list[tuple[list[str], int]], max_chars: int
) -> list[tuple[str, int]]:
    """Greedily join paragraphs up to ``max_chars``; yields ``(piece_text, start_offset)``.

    A paragraph is never split internally — cutting one open would risk a
    mid-word break — so a single paragraph longer than ``max_chars`` is
    emitted whole as its own oversized piece rather than truncated. This is
    the same trade-off the deleted chunker made for atomic blocks it could
    not split (fenced code, tables): whole-but-oversized beats fragmented.
    """
    pieces: list[tuple[str, int]] = []
    current: list[str] = []
    current_offset = 0
    current_len = 0
    for para_lines, offset in paragraphs:
        para_text = "\n".join(para_lines)
        if not current:
            current, current_offset, current_len = [para_text], offset, len(para_text)
            continue
        candidate_len = current_len + 2 + len(para_text)  # +2 for the "\n\n" joiner
        if candidate_len <= max_chars:
            current.append(para_text)
            current_len = candidate_len
        else:
            pieces.append(("\n\n".join(current), current_offset))
            current, current_offset, current_len = [para_text], offset, len(para_text)
    if current:
        pieces.append(("\n\n".join(current), current_offset))
    return pieces


def split_sections(body: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[Section, ...]:
    """Split a Markdown body (frontmatter already stripped) into embeddable sections.

    Splits on ATX headings (``#`` through ``######``); the text before the
    first heading, if any, is its own section with ``heading=""``. A section
    longer than ``max_chars`` is packed back down by joining its paragraphs
    greedily and starting a new piece once the next paragraph would overflow
    — see :func:`_pack_paragraphs` for why a paragraph itself is never split.
    A section that is only whitespace (e.g. two headings back to back with
    nothing between them) is dropped. Returns ``()`` only when the whole body
    is empty or whitespace; any body with real content yields at least one
    ``Section``.
    """
    lines = body.splitlines()
    sections: list[Section] = []
    for heading, start, end in _raw_sections(lines):
        span = lines[start:end]
        if not any(line.strip() for line in span):
            continue
        for piece_text, offset in _pack_paragraphs(_paragraphs(span), max_chars):
            sections.append(
                Section(heading=heading, text=piece_text, start_line=start + offset + 1)
            )
    return tuple(sections)


@dataclass(frozen=True)
class IndexedSection:
    """A section as the sidecar stores it: which file, where in it, its vector."""

    path: str  # knowledge-root-relative file path, e.g. "shopee/account/gateway.md"
    heading: str
    start_line: int
    vector: tuple[float, ...]


@dataclass(frozen=True)
class RankedHit:
    """One file's best-scoring section, as ``search`` reports it."""

    path: str
    score: float
    heading: str
    start_line: int


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of ``a`` and ``b``; ``0.0`` for degenerate input.

    Empty vectors, a zero-magnitude vector, and mismatched dimensions all
    score ``0.0`` rather than raising — a single malformed stored vector must
    not fail an entire :func:`rank` call over the whole corpus, it should
    just fail to match.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (norm_a * norm_b)


def rank(
    query: Sequence[float],
    sections: Iterable[IndexedSection],
    *,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
) -> tuple[RankedHit, ...]:
    """Rank ``sections`` against ``query``, one hit per file, best score first.

    A file can contribute many sections; only its best-scoring one survives,
    so a long document cannot occupy several of the ``top_k`` slots at a
    shorter file's expense (FR-024 ranks *files*, never passages). Hits
    scoring below ``min_score`` are dropped. Ties keep the lexicographically
    smaller path, so results are deterministic for a fixed corpus and query.
    An empty query vector, or ``top_k <= 0``, yields ``()``.
    """
    if top_k <= 0 or not query:
        return ()
    best: dict[str, RankedHit] = {}
    for section in sections:
        score = cosine(query, section.vector)
        if score < min_score:
            continue
        current = best.get(section.path)
        if current is None or score > current.score:
            best[section.path] = RankedHit(
                path=section.path,
                score=score,
                heading=section.heading,
                start_line=section.start_line,
            )
    ranked = sorted(best.values(), key=lambda hit: (-hit.score, hit.path))
    return tuple(ranked[:top_k])


__all__ = [
    "DEFAULT_MAX_CHARS",
    "DEFAULT_MIN_SCORE",
    "DEFAULT_TOP_K",
    "IndexedSection",
    "RankedHit",
    "Section",
    "cosine",
    "rank",
    "split_sections",
]
