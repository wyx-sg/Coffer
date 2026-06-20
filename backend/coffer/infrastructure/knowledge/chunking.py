"""Boundary-aware Markdown chunker.

Splits on ATX headings first (so a chunk never spans two sections), then packs
each section's **structural blocks** (prose paragraphs, fenced code blocks,
tables, list groups) greedily into ``chunk_size`` windows with ``chunk_overlap``
carried between adjacent chunks.

Chunk boundaries are the unit of retrieval, so they must respect structure: the
old char-window sliced blindly at ``start + chunk_size`` and split mid-fence /
mid-table, leaving orphaned half-fences and headerless table fragments that
embed and read poorly. This chunker keeps **atomic blocks** (fenced code, tables)
whole and prefers breaking at blank-line / sentence boundaries.

``chunk_size``/``chunk_overlap`` are measured in **characters** — coarse but
deterministic and dependency-free, which is what the substrate needs (the
embedding model handles real tokenization downstream). Token-based sizing is
deliberately deferred; no tokenizer is pulled in.
"""

from __future__ import annotations

import re

_HEADING_LINE = re.compile(r"^#{1,6}[ \t]+\S", re.MULTILINE)
#: A fence opener: ``` ``` ``` or ``~~~`` (3+), optionally followed by an info
#: string (language tag). The same marker char + length (or longer) closes it.
_FENCE_OPEN = re.compile(r"^([ \t]*)(`{3,}|~{3,})(.*)$")
#: Sentence-ish break points used only to split an oversized prose paragraph at
#: a natural boundary instead of mid-word: ``. ``/``! ``/``? `` (Latin) and the
#: CJK full-stop/exclamation/question marks.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])")  # noqa: RUF001


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


def _is_table_line(line: str) -> bool:
    """A table row: a non-blank line whose ``|`` actually delimits cells — it
    starts or ends with a pipe, or carries two or more. A lone in-prose pipe (a
    shell ``a | b``, an inline ``|``, a list item that happens to contain one) is
    NOT a table row, so it never fragments the surrounding prose/list block."""
    stripped = line.strip()
    if "|" not in stripped:
        return False
    return stripped.startswith("|") or stripped.endswith("|") or stripped.count("|") >= 2


def _split_blocks(section: str) -> list[str]:
    """Parse one section into ordered structural blocks.

    Blocks are: fenced code blocks (atomic, fences matched by marker), tables
    (a run of consecutive ``|``-bearing lines, atomic), and prose/list groups
    (runs of non-blank lines separated by blank lines). Blank-line runs are the
    block separators and are dropped. The heading line (first line of a section)
    is attached to the first body block so the section's heading travels with it.
    """
    lines = section.split("\n")
    blocks: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        fence = _FENCE_OPEN.match(line)
        if fence:
            # Fenced code block: consume until a matching (same char, >= length)
            # closing fence or EOF. Kept ATOMIC — fences are never split.
            marker = fence.group(2)
            close = re.compile(rf"^[ \t]*{re.escape(marker[0])}{{{len(marker)},}}[ \t]*$")
            j = i + 1
            while j < n and not close.match(lines[j]):
                j += 1
            j = min(j + 1, n)  # include the closing fence line if present
            blocks.append("\n".join(lines[i:j]))
            i = j
            continue
        if _is_table_line(line):
            # Table: a run of consecutive pipe-delimited rows (each starts/ends
            # with ``|`` or has >=2). Kept ATOMIC so no headerless fragment escapes.
            j = i + 1
            while j < n and _is_table_line(lines[j]):
                j += 1
            blocks.append("\n".join(lines[i:j]))
            i = j
            continue
        # Prose / list group: until a blank line, a fence, or a table starts.
        j = i + 1
        while j < n and lines[j].strip() and not _FENCE_OPEN.match(lines[j]):
            if _is_table_line(lines[j]):
                break
            j += 1
        blocks.append("\n".join(lines[i:j]))
        i = j
    return blocks


def _is_atomic(block: str) -> bool:
    """A fenced code block or a table — must never be split internally."""
    first = block.lstrip().split("\n", 1)[0]
    return bool(_FENCE_OPEN.match(first)) or _is_table_line(first)


def _split_oversized_prose(block: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split a prose block bigger than ``chunk_size`` at sentence boundaries
    near the target; hard-split only as a last resort (a paragraph with no
    sentence breaks at all)."""
    pieces: list[str] = []
    rest = block
    step_floor = max(1, chunk_size - chunk_overlap)
    while len(rest) > chunk_size:
        window = rest[:chunk_size]
        # Prefer the latest sentence/newline boundary inside the window so the
        # cut lands on natural prose, not mid-word.
        cut = -1
        for m in _SENTENCE_END.finditer(window):
            cut = m.end()
        nl = window.rfind("\n")
        cut = max(cut, nl + 1 if nl != -1 else -1)
        if cut <= 0:
            cut = chunk_size  # last resort: hard split a break-less paragraph
        piece = rest[:cut].strip()
        if piece:
            pieces.append(piece)
        # Carry ~chunk_overlap chars of the tail back in, but always advance.
        advance = max(step_floor, cut - chunk_overlap)
        advance = min(advance, cut)
        rest = rest[advance:]
    tail = rest.strip()
    if tail:
        pieces.append(tail)
    return pieces


def _overlap_tail(text: str, chunk_overlap: int) -> str:
    """The trailing ``~chunk_overlap`` chars of ``text``, snapped back to a block
    (blank-line) or sentence boundary so the re-included overlap reads cleanly
    rather than starting mid-word."""
    if chunk_overlap <= 0 or not text:
        return ""
    tail = text[-chunk_overlap:]
    para = tail.find("\n\n")
    if para != -1:
        return tail[para + 2 :].lstrip()
    boundary = -1
    for m in _SENTENCE_END.finditer(tail):
        boundary = m.end()
    if boundary > 0:
        return tail[boundary:].lstrip()
    return tail.lstrip()


def _pack_blocks(blocks: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    """Greedily pack whole blocks into ``chunk_size`` chunks.

    Adding a block that would overflow the current chunk flushes it and starts a
    new one (seeded with an overlap tail of the flushed chunk). An atomic block
    (fenced code / table) bigger than ``chunk_size`` is emitted WHOLE as its own
    oversized chunk — a half-fence or headerless table fragment is worse for
    retrieval than one big chunk. An oversized prose block is split at sentence
    boundaries instead.
    """
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        # The block doesn't fit with what's buffered. Flush first.
        flush()
        if len(block) <= chunk_size:
            # Seed the fresh chunk with an overlap tail of the just-flushed one.
            # If the tail + block would overflow, trim the tail (rather than drop
            # the overlap) so adjacent chunks still share context — char-exact
            # overlap is necessarily approximate once whole blocks are packed.
            overlap = _overlap_tail(chunks[-1], chunk_overlap) if chunks else ""
            room = chunk_size - len(block) - 2  # 2 for the "\n\n" joiner
            if overlap and room > 0:
                overlap = overlap[-room:].lstrip()
                current = f"{overlap}\n\n{block}" if overlap else block
            else:
                current = block
            continue
        # Oversized standalone block.
        if _is_atomic(block):
            # Atomic + oversized: keep WHOLE (trade-off documented above). The
            # next chunk starts with no overlap tail — re-including the tail of a
            # code block / table into the following prose would be meaningless.
            chunks.append(block.strip())
            current = ""
            continue
        pieces = _split_oversized_prose(block, chunk_size, chunk_overlap)
        chunks.extend(pieces[:-1])
        current = pieces[-1] if pieces else ""
    flush()
    return chunks


def chunk_markdown(markdown: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Return ordered, boundary-aware chunks for ``markdown``.

    Empty/whitespace input yields ``[]``. Overlap is clamped to ``< chunk_size``.
    Chunks never span two heading sections, never split a fenced code block or a
    table, and pack whole structural blocks greedily up to ``chunk_size``.
    """
    if not markdown.strip():
        return []
    overlap = max(0, min(chunk_overlap, chunk_size - 1))
    chunks: list[str] = []
    for section in _split_sections(markdown):
        blocks = _split_blocks(section)
        if not blocks:
            continue
        chunks.extend(_pack_blocks(blocks, chunk_size, overlap))
    return chunks
