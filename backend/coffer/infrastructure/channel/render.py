"""Outbound rendering: markdown → Telegram-safe HTML, plus chunking.

Telegram MarkdownV2 is an escaping minefield; the proven pattern (research.md)
is rendering a small markdown subset to HTML ``parse_mode`` and retrying as
plain text if the platform rejects it. Only tags Telegram documents are
emitted: b / i / code / pre / a.
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
    text = _HEADING.sub(lambda m: f"<b>{m.group(1)}</b>", text)
    text = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = _BOLD.sub(lambda m: f"<b>{m.group(1)}</b>", text)
    text = _ITALIC.sub(lambda m: f"<i>{m.group(1) or m.group(2)}</i>", text)
    for i, span in enumerate(spans):
        text = text.replace(f"\x00{i}\x00", f"<code>{span}</code>")
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
