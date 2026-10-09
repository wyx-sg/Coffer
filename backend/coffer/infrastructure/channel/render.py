"""Outbound rendering: one markdown subset → each platform's own text format,
plus chunking.

Telegram MarkdownV2 is an escaping minefield; the proven pattern (ADR channel-adapter-framework)
is rendering a small markdown subset to HTML ``parse_mode`` and retrying as
plain text if the platform rejects it. Only tags Telegram documents are
emitted: b / i / code / pre / a.

SeaTalk has its own markdown (``format: 1``) — bold, italic, inline code, code
fences, ordered/unordered lists — with neither headings nor links, and a
literal marker character is escaped with a SINGLE backslash. Its renderer
lives beside Telegram's so both read from the same regex vocabulary.
"""

from __future__ import annotations

import html
import re

_CODE_FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)|\b_([^_\n]+)_\b")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+|tg://user\?id=\d+)\)")
_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
# A line-leading "- " / "* " (with optional indent) is a markdown bullet. Telegram
# HTML has no list element, so render a tidy "• " glyph rather than a raw dash. The
# trailing-whitespace requirement keeps it from matching **bold** / *italic*.
_BULLET = re.compile(r"^([ \t]*)[-*][ \t]+", re.MULTILINE)


def markdown_to_telegram_html(markdown: str) -> str:
    """Render a pragmatic markdown subset to Telegram HTML."""
    out: list[str] = []
    last = 0
    for match in _CODE_FENCE.finditer(markdown):
        out.append(_inline(markdown[last : match.start()]))
        out.append(f"<pre>{html.escape(match.group(1).rstrip())}</pre>")
        last = match.end()
    out.append(_inline(markdown[last:]))
    return "".join(out).strip()


def _inline(text: str) -> str:
    """Escape, then re-introduce the supported inline tags."""
    # Protect inline code spans before any other transformation.
    spans: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        spans.append(html.escape(m.group(1)))
        return f"\x00{len(spans) - 1}\x00"

    text = _INLINE_CODE.sub(_stash, text)
    text = html.escape(text, quote=False)
    text = _BULLET.sub(lambda m: f"{m.group(1)}• ", text)
    text = _HEADING.sub(lambda m: f"<b>{m.group(1)}</b>", text)
    text = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = _BOLD.sub(lambda m: f"<b>{m.group(1)}</b>", text)
    text = _ITALIC.sub(lambda m: f"<i>{m.group(1) or m.group(2)}</i>", text)
    for i, span in enumerate(spans):
        text = text.replace(f"\x00{i}\x00", f"<code>{span}</code>")
    return text


# SeaTalk's own markdown: the characters that start formatting there, so any
# one of them left over after the supported constructs are lifted out must be
# escaped (with a SINGLE backslash) to survive as a literal. Angle brackets are
# deliberately absent: a live probe confirmed `<` and `>` reach the chat as
# written, so escaping them would only add visible noise.
_SEATALK_MARKER = re.compile(r"[*_`~]")
_BARE_URL = re.compile(r"https?://\S+")
# `*` / `+` bullets → the `-` form; a bullet needs trailing whitespace, so
# **bold** at line start is never mistaken for one.
_ALT_BULLET = re.compile(r"^([ \t]*)[*+]([ \t]+)", re.MULTILINE)
#: A SeaTalk @mention ("Mention the asker in a group answer"): markup Coffer put there itself, and
#: the ONE span no escaping pass may touch. A single backslash inside it is enough to turn a
#: rendered name into visible tag source, and the target legitimately carries characters this
#: module escapes — an id may contain `_`, and the email form of the tag
#: (``?email=first_last@example.com``) very often does. So it is stashed out of the way like inline
#: code, not trusted to be marker-free.
_MENTION_TAG = re.compile(r'<mention-tag\s+target="[^"]*"\s*/>')


def markdown_to_seatalk(markdown: str) -> str:
    """Render the same markdown subset to SeaTalk markdown (``format: 1``).

    Bold, italic, inline code, fenced code and lists pass through as SeaTalk's
    own syntax; headings become bold and links become ``label (url)`` because
    SeaTalk supports neither. Tables are left as written — they render in a
    text message but NOT inside a card's description, which is why selection
    cards stay short prompts.
    """
    out: list[str] = []
    last = 0
    for match in _CODE_FENCE.finditer(markdown):
        out.append(_seatalk_inline(markdown[last : match.start()]))
        out.append("```\n" + match.group(1).strip("\n") + "\n```")
        last = match.end()
    out.append(_seatalk_inline(markdown[last:]))
    return "".join(out).strip()


def _seatalk_inline(text: str) -> str:
    """Lift every supported construct out, escape what is left, put them back."""
    spans: list[str] = []

    def stash(rendered: str) -> str:
        spans.append(rendered)
        return f"\x00{len(spans) - 1}\x00"

    # An @mention first of all: it is markup Coffer built, and its target can
    # hold a character this renderer escapes (an id with `_`, or the email form
    # of the tag), which would reach the reader as visible tag source.
    text = _MENTION_TAG.sub(lambda m: stash(m.group(0)), text)
    text = _INLINE_CODE.sub(lambda m: stash(f"`{m.group(1)}`"), text)
    # Links first: they carry a URL the bare-URL rule would otherwise swallow.
    text = _LINK.sub(lambda m: stash(f"{m.group(1)} ({m.group(2)})"), text)
    text = _BARE_URL.sub(lambda m: stash(m.group(0)), text)
    text = _HEADING.sub(lambda m: stash(f"**{m.group(1)}**"), text)
    text = _ALT_BULLET.sub(lambda m: f"{m.group(1)}-{m.group(2)}", text)
    text = _BOLD.sub(lambda m: stash(f"**{m.group(1)}**"), text)
    text = _ITALIC.sub(lambda m: stash(f"*{m.group(1) or m.group(2)}*"), text)
    # One backslash is SeaTalk's escape, so `snake_case` survives as typed
    # instead of being read as half an italic run. Two would be one escape too
    # many: SeaTalk consumes the first and shows the second as literal text.
    text = _SEATALK_MARKER.sub(lambda m: "\\" + m.group(0), text)
    for i, span in enumerate(spans):
        text = text.replace(f"\x00{i}\x00", span)
    return text


_FENCE_LINE = re.compile(r"^[ \t]*```")


def _blocks(text: str) -> list[str]:
    """Paragraphs, except that a fenced code block is ONE block however many
    blank lines it holds — a chunk boundary inside a fence renders as two
    broken halves on every platform."""
    blocks: list[str] = []
    open_fence = False
    for paragraph in text.split("\n\n"):
        if open_fence and blocks:
            blocks[-1] += "\n\n" + paragraph
        else:
            blocks.append(paragraph)
        for line in paragraph.split("\n"):
            if _FENCE_LINE.match(line):
                open_fence = not open_fence
    return blocks


def _split_fence(block: str, limit: int) -> list[str]:
    """Cut an oversized fenced block at line boundaries, closing each piece
    and reopening the next with the same opening line (language kept)."""
    lines = block.split("\n")
    opener = lines[0] if _FENCE_LINE.match(lines[0]) else "```"
    body = lines[1:-1] if len(lines) > 1 and _FENCE_LINE.match(lines[-1]) else lines[1:]
    room = max(limit - len(opener) - 5, 1)
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for line in body:
        while len(line) > room:  # one line longer than a whole piece
            if current:
                pieces.append("\n".join(current))
                current, size = [], 0
            pieces.append(line[:room])
            line = line[room:]
        if current and size + len(line) + 1 > room:
            pieces.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        pieces.append("\n".join(current))
    return [f"{opener}\n{piece}\n```" for piece in pieces]


def _fence_segments(block: str) -> list[tuple[bool, str]]:
    """``(is_fence, text)`` runs of a block: its prose and its fenced code,
    wherever in the block a fence starts."""
    segments: list[tuple[bool, list[str]]] = []
    open_fence = False
    for line in block.split("\n"):
        starts = bool(_FENCE_LINE.match(line))
        if starts and not open_fence:
            segments.append((True, [line]))
            open_fence = True
            continue
        if not segments or segments[-1][0] != open_fence:
            segments.append((open_fence, []))
        segments[-1][1].append(line)
        if starts:
            open_fence = False
    return [(is_fence, "\n".join(lines)) for is_fence, lines in segments]


def _split_prose(text: str, limit: int) -> list[str]:
    pieces: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        cut = cut if cut > limit // 2 else limit
        pieces.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return [*pieces, text]


def _hard_split(block: str, limit: int) -> list[str]:
    """Cut an oversized block, never through the middle of a fenced code block:
    its prose is cut at newlines, its fences at line boundaries with each piece
    closed and reopened. A fence that starts partway through the block (``Here
    is the log:`` followed by a fence) is a fence like any other."""
    pieces: list[str] = []
    for is_fence, text in _fence_segments(block):
        if len(text) <= limit:
            pieces.append(text)
        elif is_fence:
            pieces += _split_fence(text, limit)
        else:
            pieces += _split_prose(text, limit)
    return [piece for piece in pieces if piece.strip()]


def chunk_text(text: str, limit: int) -> list[str]:
    """Split on paragraph boundaries into chunks of at most ``limit`` chars.

    Never inside a fenced code block: a fence is kept whole, and one longer
    than ``limit`` is closed and reopened at a line boundary. Any other
    paragraph longer than ``limit`` is split at a newline where one is near,
    else hard. Returns at least one chunk for non-empty input; empty input
    yields no chunks.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for block in _blocks(text):
        pieces = _hard_split(block, limit) if len(block) > limit else [block]
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) > limit:
                if current:
                    chunks.append(current)
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current)
    return [c for c in (chunk.strip() for chunk in chunks) if c]
