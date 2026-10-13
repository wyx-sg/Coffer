"""Storage Format XML → Markdown: the walker (design §5, "Storage → Markdown").

The Storage XML is parsed as HTML with CDATA sections turned into escaped text
first, so a ``<module>`` inside a code macro survives as text. :class:`Walker`
renders block elements to a list of Markdown blocks and inline elements to a
string; macros, tables and Confluence references are delegated to their own
modules.
"""

from __future__ import annotations

from bs4 import Comment, Declaration, Doctype, ProcessingInstruction, Tag
from bs4.element import NavigableString, PageElement

from coffer.infrastructure.knowledge.converters.confluence import diagrams, macros, refs, tables
from coffer.infrastructure.knowledge.converters.confluence.kept import Kept
from coffer.infrastructure.knowledge.converters.confluence.text import (
    BREAK,
    SPACE,
    code_span,
    escape_text,
    fence,
    finish_paragraph,
    link,
    list_item,
    parse,
    quote,
    wrap,
)

_HEADINGS = {f"h{n}": n for n in range(1, 7)}
_CONTAINERS = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "main",
        "body",
        "center",
        "ac:rich-text-body",
        "ac:layout",
        "ac:layout-section",
        "ac:layout-cell",
        "ac:task-body",
    }
)
_BLOCKS = (
    _CONTAINERS | set(_HEADINGS) | {"ul", "ol", "table", "pre", "blockquote", "hr", "ac:task-list"}
)
_SKIPPED = frozenset({"colgroup", "col", "script", "style", "ac:parameter", "head", "title"})


class Walker:
    """Renders one Storage document against one :class:`Kept`."""

    def __init__(self, kept: Kept) -> None:
        self.kept = kept

    # -- entry ---------------------------------------------------------------

    def markdown(self, storage: str) -> str:
        blocks = self.blocks(parse(storage))
        return "\n\n".join(b for b in blocks if b.strip()) + "\n" if blocks else ""

    # -- classification ------------------------------------------------------

    @staticmethod
    def is_block(tag: Tag) -> bool:
        if tag.name in _BLOCKS:
            return True
        if macros.is_macro(tag):
            return not macros.is_inline(tag)
        return False

    # -- blocks --------------------------------------------------------------

    def blocks(self, container: Tag) -> list[str]:
        out: list[str] = []
        run: list[str] = []

        def flush() -> None:
            paragraph = finish_paragraph("".join(run))
            if paragraph:
                out.append(paragraph)
            run.clear()

        for child in container.children:
            if isinstance(child, Tag):
                if child.name in _SKIPPED:
                    continue
                if self.is_block(child):
                    flush()
                    out.extend(b for b in self.block(child) if b.strip())
                else:
                    run.append(self.inline(child))
            else:
                run.append(self.text(child))
        flush()
        return out

    def block(self, tag: Tag) -> list[str]:
        name = tag.name
        if macros.is_macro(tag):
            return macros.block(self, tag)
        if name in _HEADINGS:
            text = finish_paragraph(self.inline_children(tag), " ")
            return [f"{'#' * _HEADINGS[name]} {text}"] if text else []
        if name in ("ul", "ol"):
            return self.list_block(tag, ordered=name == "ol")
        if name == "table":
            return tables.render(self, tag)
        if name == "pre":
            return [fence(tag.get_text())]
        if name == "blockquote":
            return [quote(self.blocks(tag))]
        if name == "hr":
            return ["---"]
        if name == "ac:task-list":
            return refs.task_list(self, tag)
        return self.blocks(tag)

    def list_block(self, tag: Tag, *, ordered: bool) -> list[str]:
        items: list[str] = []
        for number, item in enumerate(tag.find_all("li", recursive=False), start=1):
            marker = f"{number}. " if ordered else "- "
            items.append(list_item(marker, self.blocks(item)))
        return ["\n".join(items)] if items else []

    # -- inline --------------------------------------------------------------

    def text(self, node: PageElement) -> str:
        if isinstance(node, (Comment, Declaration, Doctype, ProcessingInstruction)):
            return ""
        if isinstance(node, NavigableString):
            return escape_text(SPACE.sub(" ", str(node)))
        return ""

    def inline_children(self, tag: Tag) -> str:
        parts: list[str] = []
        for child in tag.children:
            if isinstance(child, Tag):
                if child.name in _SKIPPED:
                    continue
                parts.append(self.inline(child))
            else:
                parts.append(self.text(child))
        return "".join(parts)

    def inline(self, tag: Tag) -> str:
        name = tag.name
        if macros.is_macro(tag):
            if macros.is_inline(tag):
                return macros.inline(self, tag)
            return " " + " ".join(self.block(tag)) + " "
        if name in ("strong", "b"):
            return wrap(self.inline_children(tag), "**")
        if name in ("em", "i"):
            return wrap(self.inline_children(tag), "*")
        if name in ("s", "del", "strike"):
            return wrap(self.inline_children(tag), "~~")
        if name in ("code", "tt", "kbd", "samp"):
            return code_span(tag.get_text())
        if name == "br":
            return BREAK
        if name == "a":
            return self.anchor(tag)
        if name == "img":
            return refs.plain_image(self, tag)
        if name == "ac:image":
            return refs.image(self, tag)
        if name == "ac:link":
            return refs.link_text(self, tag)
        if name == "ac:emoticon":
            shortname = tag.get("ac:emoji-shortname") or tag.get("ac:name") or ""
            return f":{str(shortname).strip(':')}:" if shortname else ""
        if name == "ac:placeholder":
            return ""
        if name == "time":
            return escape_text(str(tag.get("datetime") or tag.get_text()))
        if name.startswith("ri:"):
            return ""
        if self.is_block(tag):
            return " " + " ".join(self.block(tag)) + " "
        return self.inline_children(tag)

    def anchor(self, tag: Tag) -> str:
        href = str(tag.get("href") or "")
        text = self.inline_children(tag)
        if href and diagrams.is_diagram_url(href) and diagrams.carries_diagram(href):
            return diagrams.diagram_url(self.kept, href, finish_paragraph(text, " "))
        return link(text, href)
