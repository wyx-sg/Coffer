"""Markdown text helpers shared by the Storage walker, its macros and tables."""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
SPACE = re.compile(r"[ \t\r\n\f\xa0]+")
#: A hard line break inside a paragraph, replaced once the paragraph is known.
BREAK = "\x00"
_BREAKS = re.compile(r"\s*\x00[\x00\s]*")
_SAFE_SCHEMES = ("http://", "https://", "mailto:", "#")
_LIST_START = re.compile(r"(?:[-*] |\d+\. )")


def parse(storage: str) -> BeautifulSoup:
    """Parse Storage XML as HTML, CDATA kept as (escaped) text."""
    escaped = _CDATA.sub(lambda m: html.escape(m.group(1), quote=False), storage)
    return BeautifulSoup(escaped, "html.parser")


_MARKDOWN_PUNCTUATION = re.compile(r"([\\`*\[\]])")


def escape_text(text: str) -> str:
    """Plain text made safe to place in Markdown: no raw HTML, emphasis, code
    span or link (wiki or standard) can start from it."""
    text = _MARKDOWN_PUNCTUATION.sub(r"\\\1", text)
    return text.replace("&", "&amp;").replace("<", "&lt;")


def fence(text: str, language: str = "") -> str:
    """``text`` verbatim in a fenced block long enough not to be closed by it."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    body = text.strip("\n")
    return f"{ticks}{language}\n{body}\n{ticks}"


def code_span(text: str) -> str:
    text = SPACE.sub(" ", text).strip()
    if not text:
        return ""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    ticks = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{ticks}{pad}{text}{pad}{ticks}"


def wrap(content: str, mark: str) -> str:
    stripped = content.strip()
    if not stripped:
        return content
    lead = " " if content[:1].isspace() else ""
    trail = " " if content[-1:].isspace() else ""
    return f"{lead}{mark}{stripped}{mark}{trail}"


def link(text: str, href: str) -> str:
    """A Markdown link; an unsafe target (``javascript:`` …) keeps the text only."""
    href = href.strip()
    if not href.lower().startswith(_SAFE_SCHEMES):
        return text
    label = text.strip() or escape_text(href)
    target = f"<{href}>" if re.search(r"[\s()<>]", href) else href
    return f"[{label}]({target})"


def finish_paragraph(text: str, hard_break: str = "\\\n") -> str:
    text = _BREAKS.sub(BREAK, text).strip(BREAK + " ")
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.replace(BREAK, hard_break).strip()


def quote(blocks: list[str]) -> str:
    body = "\n\n".join(blocks)
    return "\n".join(f"> {line}" if line else ">" for line in body.split("\n"))


def list_item(marker: str, blocks: list[str]) -> str:
    if not blocks:
        return marker.rstrip()
    text = blocks[0]
    for block in blocks[1:]:
        text += ("\n" if _LIST_START.match(block) else "\n\n") + block
    indent = " " * len(marker)
    lines = text.split("\n")
    rest = [f"{indent}{line}" if line else "" for line in lines[1:]]
    return "\n".join([marker + lines[0], *rest])
