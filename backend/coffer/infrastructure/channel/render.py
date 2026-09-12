"""Outbound rendering: one markdown subset → each platform's own text format,
plus chunking.

Telegram MarkdownV2 is an escaping minefield; the proven pattern (research.md)
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
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
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
#: A SeaTalk @mention (FR-070): markup Coffer put there itself, and the ONE span
#: no escaping pass may touch. A single backslash inside it is enough to turn a
#: rendered name into visible tag source, and the target legitimately carries
#: characters this module escapes — an id may contain `_`, and the email form of
#: the tag (``?email=first_last@example.com``) very often does. So it is stashed
#: out of the way like inline code, not trusted to be marker-free.
_MENTION_TAG = re.compile(r'<mention-tag\s+target="[^"]*"\s*/>')


def split_leading_mention(text: str) -> tuple[str, str]:
    """``(mention prefix, rest)`` — the @mention opening ``text``, if any.

    The prefix INCLUDES the whitespace that separates it from the body, so
    ``prefix + rest`` is ``text`` byte for byte. Callers that shorten a snapshot
    from the front (an interim stream update keeps the newest words) split here
    first, so the clipping cannot eat the mention the message must keep.
    """
    match = _MENTION_TAG.match(text)
    if match is None:
        return "", text
    end = match.end()
    while end < len(text) and text[end] in " \t":
        end += 1
    return text[:end], text[end:]


def escape_seatalk_literal(text: str) -> str:
    """Escape every SeaTalk markdown marker in ``text``, leaving @mentions alone.

    For text that must reach the chat AS WRITTEN inside a ``format: 1`` message:
    an interim stream snapshot, which is a reply clipped mid-word and can end
    inside an unclosed ``*`` or ``_``. Asking the client to parse that renders
    noise, so nothing here is interpreted — but the snapshot still has to be
    ``format: 1``, because the message it belongs to carries a mention tag, and
    a tag is only a name in a rich message.

    ONE backslash per marker: SeaTalk consumes it and shows the character.
    """
    spans: list[str] = []

    def stash(match: re.Match[str]) -> str:
        spans.append(match.group(0))
        return f"\x00{len(spans) - 1}\x00"

    text = _MENTION_TAG.sub(stash, text)
    text = _SEATALK_MARKER.sub(lambda m: "\\" + m.group(0), text)
    for i, span in enumerate(spans):
        text = text.replace(f"\x00{i}\x00", span)
    return text


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


def chunk_text(text: str, limit: int) -> list[str]:
    """Split on paragraph boundaries into chunks of at most ``limit`` chars.

    A single paragraph longer than ``limit`` is hard-split. Returns at least
    one chunk for non-empty input; empty input yields no chunks.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        while len(paragraph) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > limit:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return [c for c in (chunk.strip() for chunk in chunks) if c]
